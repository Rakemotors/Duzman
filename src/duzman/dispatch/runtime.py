# src/duzman/dispatch/runtime.py
# Dispatch runtime service. Composes sender, optional AI worker, and delivery
# persistence for scheduler/runtime wiring with idempotent send reservation.
"""Runtime dispatch composition for persisted pattern trigger events."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from duzman.dispatch.ai_worker import DispatchAIExplanationResult
from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.persistence.mapping import delivery_row_from_telegram_result
from duzman.dispatch.persistence.repository import (
    DISPATCH_DELIVERY_DIALECT_POSTGRESQL,
    DispatchDeliveryDialect,
    DispatchDeliveryRepository,
)
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_SENDING,
    TELEGRAM_CHANNEL,
    AlertDeliveryRow,
    RecordDeliveryResult,
)
from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_API,
    TELEGRAM_STATUS_FAILED,
    TelegramSendResult,
)

LOGGER = logging.getLogger(__name__)


class DispatchTelegramSender(Protocol):
    """Telegram sender capability required by runtime dispatch."""

    async def send(self, event: DispatchEvent) -> TelegramSendResult:
        """Send one dispatch event and return a bounded Telegram result."""


class DispatchAIWorker(Protocol):
    """Optional AI explanation capability required by runtime dispatch."""

    async def explain(self, event: DispatchEvent) -> DispatchAIExplanationResult:
        """Generate or reuse an explanation for one dispatch event."""


RepositoryFactory = Callable[[AsyncSession], DispatchDeliveryRepository]


class SessionFactory(Protocol):
    """Factory that creates async SQLAlchemy session context managers."""

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return a new async session context manager."""


@dataclass(frozen=True)
class RuntimeDispatchResult:
    """Result for one event processed by the runtime dispatch service."""

    event: DispatchEvent
    reservation: RecordDeliveryResult
    telegram_result: TelegramSendResult | None
    ai_result: DispatchAIExplanationResult | None


class DispatchRuntimeService:
    """Dispatch persisted pattern trigger events with idempotent delivery rows."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        sender: DispatchTelegramSender,
        ai_worker: DispatchAIWorker | None = None,
        enabled: bool = False,
        repository_factory: RepositoryFactory | None = None,
        dialect: DispatchDeliveryDialect = DISPATCH_DELIVERY_DIALECT_POSTGRESQL,
    ) -> None:
        """Create a runtime dispatch service with explicit dependencies."""
        self._session_factory = session_factory
        self._sender = sender
        self._ai_worker = ai_worker
        self._enabled = enabled
        self._repository_factory = repository_factory
        self._dialect = dialect

    async def dispatch_events(
        self,
        events: list[DispatchEvent],
    ) -> list[RuntimeDispatchResult]:
        """Dispatch events sequentially and return one result per input event."""
        results: list[RuntimeDispatchResult] = []
        for event in events:
            if not self._enabled:
                LOGGER.info(
                    "dispatch_runtime_disabled",
                    extra={"pattern_trigger_id": event.pattern_trigger_id},
                )
                continue

            reservation = await self._reserve_delivery(event)
            if not reservation.persisted:
                LOGGER.info(
                    "dispatch_delivery_duplicate_skipped",
                    extra={"pattern_trigger_id": event.pattern_trigger_id},
                )
                results.append(
                    RuntimeDispatchResult(
                        event=event,
                        reservation=reservation,
                        telegram_result=None,
                        ai_result=None,
                    )
                )
                continue

            assert reservation.row_id is not None
            telegram_result = await self._send_safely(event)
            await self._finalize_delivery(
                row_id=reservation.row_id,
                event=event,
                telegram_result=telegram_result,
            )
            ai_result = await self._explain_safely(event)
            results.append(
                RuntimeDispatchResult(
                    event=event,
                    reservation=reservation,
                    telegram_result=telegram_result,
                    ai_result=ai_result,
                )
            )
        return results

    async def _reserve_delivery(self, event: DispatchEvent) -> RecordDeliveryResult:
        """Reserve the Telegram delivery idempotency key before sending."""
        row = AlertDeliveryRow(
            pattern_trigger_id=event.pattern_trigger_id,
            channel=TELEGRAM_CHANNEL,
            status=DELIVERY_STATUS_SENDING,
            telegram_message_id=None,
            error_message=None,
            sent_at=None,
        )
        async with self._session_factory() as session:
            async with session.begin():
                return await self._repository(session).record_delivery(row)

    async def _finalize_delivery(
        self,
        *,
        row_id: int,
        event: DispatchEvent,
        telegram_result: TelegramSendResult,
    ) -> None:
        """Persist the terminal Telegram delivery result for a reserved row."""
        row = delivery_row_from_telegram_result(
            event=event,
            result=telegram_result,
            now=event.ts,
        )
        async with self._session_factory() as session:
            async with session.begin():
                await self._repository(session).finalize_delivery(
                    row_id=row_id,
                    row=row,
                    completed_at=event.ts,
                )

    async def _send_safely(self, event: DispatchEvent) -> TelegramSendResult:
        """Send one event and map sender exceptions into a failed result."""
        try:
            return await self._sender.send(event)
        except Exception:
            LOGGER.exception(
                "dispatch_telegram_send_failed",
                extra={"pattern_trigger_id": event.pattern_trigger_id},
            )
            return TelegramSendResult(
                status=TELEGRAM_STATUS_FAILED,
                telegram_message_id=None,
                error_reason=TELEGRAM_ERROR_API,
                attempts=1,
            )

    async def _explain_safely(
        self,
        event: DispatchEvent,
    ) -> DispatchAIExplanationResult | None:
        """Run optional AI explanation without failing Telegram dispatch."""
        if self._ai_worker is None:
            return None
        try:
            return await self._ai_worker.explain(event)
        except Exception:
            LOGGER.exception(
                "dispatch_ai_explanation_failed",
                extra={"pattern_trigger_id": event.pattern_trigger_id},
            )
            return None

    def _repository(self, session: AsyncSession) -> DispatchDeliveryRepository:
        """Build a dispatch delivery repository for one runtime session."""
        if self._repository_factory is not None:
            return self._repository_factory(session)
        return DispatchDeliveryRepository(session, dialect=self._dialect)
