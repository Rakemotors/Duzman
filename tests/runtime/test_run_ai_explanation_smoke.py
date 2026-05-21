from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from duzman.ai.app import AiWorkerComponents
from duzman.ai.explanation_service import ExplanationService
from duzman.ai.explanation_worker import ExplanationWorker
from duzman.db.models import AlertDelivery, AlertExplanation, PatternTrigger
from duzman.runtime.run_ai_explanation_smoke import (
    AiExplanationSmokeSettings,
    _async_main,
    _build_parser,
    main,
)
from duzman.settings import Settings
from duzman.telegram.sender import TelegramAlertSender
from tests.telegram.test_sender import _create_tables, _insert_alert


class FakeWorker:
    """Explanation worker test double for smoke entrypoint tests."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        final_status: str = "completed",
        text: str | None = "AI explanation",
    ) -> None:
        self._session_factory = session_factory
        self._final_status = final_status
        self._text = text

    async def run_once(self) -> int:
        """Process one pending explanation row."""
        async with self._session_factory() as session:
            explanation = await session.scalar(
                select(AlertExplanation).where(AlertExplanation.status == "pending")
            )
            if explanation is None:
                return 0
            explanation.status = self._final_status
            explanation.text = self._text
            explanation.total_tokens = 7
            await session.commit()
            return 1


class FakeEngine:
    """Async engine test double with no-op disposal."""

    async def dispose(self) -> None:
        """Do not dispose the real SQLite engine owned by the fixture."""


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an async SQLite session factory for AI explanation smoke tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_explanation_smoke_happy_path(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 smoke should create and complete one explanation row."""
    trigger_id = await _seed_smoke_delivery(session_factory)

    exit_code = await _run_async_main(
        ["--trigger-id", str(trigger_id)],
        settings_provider=_enabled_settings,
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    async with session_factory() as session:
        explanation = await session.scalar(select(AlertExplanation))

    assert exit_code == 0
    assert explanation is not None
    assert explanation.status == "completed"
    assert "AI_EXPLANATION_SMOKE_OK alert_explanation_id=" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_ai_explanation_smoke_rolls_back_rows(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 rollback should remove only the smoke chain rows."""
    trigger_id = await _seed_smoke_delivery(session_factory)

    exit_code = await _run_async_main(
        ["--trigger-id", str(trigger_id), "--rollback"],
        settings_provider=_enabled_settings,
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    async with session_factory() as session:
        triggers = list(await session.scalars(select(PatternTrigger)))
        deliveries = list(await session.scalars(select(AlertDelivery)))
        explanations = list(await session.scalars(select(AlertExplanation)))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SMOKE_ROLLBACK_OK" in output
    assert triggers == []
    assert deliveries == []
    assert explanations == []


@pytest.mark.asyncio
async def test_ai_explanation_smoke_idempotent_rollback_noop(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 repeated rollback should succeed when the trigger is already missing."""
    exit_code = await _run_async_main(
        ["--trigger-id", "999", "--rollback"],
        settings_provider=_enabled_settings,
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    assert exit_code == 0
    assert "SMOKE_ROLLBACK_NOOP" in capsys.readouterr().out


def test_ai_explanation_smoke_rejects_disabled_ai(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 smoke should return exit 2 when AI explanations are disabled."""
    exit_code = main(
        ["--trigger-id", "1"],
        settings_provider=lambda: AiExplanationSmokeSettings(
            ai_explanations_enabled=False,
            anthropic_api_key="key",
        ),
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    assert exit_code == 2
    assert "AI_EXPLANATIONS_ENABLED must be true" in capsys.readouterr().out


def test_ai_explanation_smoke_rejects_missing_key(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 smoke should return exit 2 when Anthropic key is missing."""
    exit_code = main(
        ["--trigger-id", "1"],
        settings_provider=lambda: AiExplanationSmokeSettings(
            ai_explanations_enabled=True,
            anthropic_api_key="",
        ),
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    assert exit_code == 2
    assert "missing ANTHROPIC_API_KEY" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_ai_explanation_smoke_rejects_non_smoke_trigger(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 smoke should not process production-looking triggers."""
    async with session_factory() as session:
        trigger = await _insert_alert(session)
        await session.commit()
        trigger_id = int(trigger.id)

    exit_code = await _run_async_main(
        ["--trigger-id", str(trigger_id)],
        settings_provider=_enabled_settings,
        product_settings_provider=_product_settings,
        components_builder=_components_builder(session_factory),
    )

    assert exit_code == 2
    assert "trigger is not a smoke_b0 trigger" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_ai_explanation_smoke_returns_exit_3_when_worker_not_done(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B1 smoke should return exit 3 when worker leaves explanation failed."""
    trigger_id = await _seed_smoke_delivery(session_factory)

    exit_code = await _run_async_main(
        ["--trigger-id", str(trigger_id)],
        settings_provider=_enabled_settings,
        product_settings_provider=_product_settings,
        components_builder=_components_builder(
            session_factory,
            final_status="failed",
            text=None,
        ),
    )

    assert exit_code == 3
    assert "AI_EXPLANATION_SMOKE_NOT_DONE status=failed" in capsys.readouterr().out


async def _seed_smoke_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """Create one B0-like trigger and sent Telegram delivery."""
    async with session_factory() as session:
        trigger = PatternTrigger(
            asset="BTC",
            pattern_name="smoke_b0",
            severity="INFO",
            ts=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
            conditions_snapshot={"smoke": True, "gate_decision": "ALLOW"},
            alert_sent=True,
        )
        session.add(trigger)
        await session.flush()
        session.add(
            AlertDelivery(
                alert_id=int(trigger.id),
                channel="telegram",
                status="sent",
                telegram_message_id=321,
            )
        )
        await session.commit()
        return int(trigger.id)


def _enabled_settings() -> AiExplanationSmokeSettings:
    """Return valid B1 smoke settings."""
    return AiExplanationSmokeSettings(
        ai_explanations_enabled=True,
        anthropic_api_key="key",
        ai_explanation_max_per_hour=3,
        ai_explanation_max_per_day=5,
    )


def _product_settings() -> Settings:
    """Return an unused Settings placeholder for the injected component builder."""
    return cast(Settings, object())


async def _run_async_main(
    argv: list[str],
    *,
    settings_provider: Callable[[], AiExplanationSmokeSettings],
    product_settings_provider: Callable[[], Settings],
    components_builder: Callable[[Settings], AiWorkerComponents],
) -> int:
    """Run the private async entrypoint without nesting asyncio.run in tests."""
    args = _build_parser().parse_args(argv)
    return await _async_main(
        args,
        settings_provider=settings_provider,
        product_settings_provider=product_settings_provider,
        components_builder=components_builder,
    )


def _components_builder(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    final_status: str = "completed",
    text: str | None = "AI explanation",
) -> Callable[[Settings], AiWorkerComponents]:
    """Build fake AI worker components for tests."""

    def build(_: Settings) -> AiWorkerComponents:
        return AiWorkerComponents(
            async_engine=cast(Any, FakeEngine()),
            session_factory=session_factory,
            explanation_service=cast(ExplanationService, object()),
            worker=cast(
                ExplanationWorker,
                FakeWorker(session_factory, final_status=final_status, text=text),
            ),
            telegram_sender=cast(TelegramAlertSender, object()),
        )

    return build
