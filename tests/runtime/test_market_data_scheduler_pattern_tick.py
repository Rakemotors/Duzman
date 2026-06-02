# tests/runtime/test_market_data_scheduler_pattern_tick.py
# Runtime scheduler tests for Phase 1 Pattern Engine tick wiring.
# Verifies engine-per-tick ownership and offline observation-only execution.
"""Tests for the market data scheduler pattern tick job."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace, TracebackType
from typing import Any, cast

import pytest
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import duzman.runtime.market_data_scheduler as market_data_scheduler
from duzman.db.session_async import AsyncDatabaseSessionComponents
from duzman.dispatch.persistence.repository import DISPATCH_DELIVERY_DIALECT_POSTGRESQL
from duzman.patterns.snapshot import AssetMetrics, MetricsSnapshot
from duzman.runtime.market_data_scheduler import (
    HOURLY_PATTERN_TICK_JOB_ID,
    _default_pattern_dispatch_factory,
    _run_observation_only_pattern_tick_cycle,
    build_market_data_scheduler,
)


def _unused_sync_session_factory() -> Any:
    """Fail if pattern tick tests accidentally execute sync scheduler jobs."""
    raise AssertionError(
        "sync session_factory should not be used by pattern tick tests"
    )


def test_scheduler_registers_pattern_tick_job() -> None:
    """The runtime scheduler should register the Phase 1 pattern tick job."""
    scheduler = build_market_data_scheduler(
        session_factory=_unused_sync_session_factory,
    )

    jobs_by_id = {job.id: job for job in scheduler.get_jobs()}
    pattern_job = jobs_by_id[HOURLY_PATTERN_TICK_JOB_ID]

    assert isinstance(pattern_job.trigger, CronTrigger)
    trigger_text = str(pattern_job.trigger)
    assert "minute='33'" in trigger_text
    assert "second='0'" in trigger_text
    assert str(pattern_job.trigger.timezone) == "UTC"


def test_pattern_tick_job_runs_with_injected_dependencies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The registered pattern tick callable should run offline and log completion."""
    components_factory = _EnginePerTickComponentsFactory()
    scheduler = build_market_data_scheduler(
        session_factory=_unused_sync_session_factory,
        pattern_session_components_factory=components_factory,
        pattern_dispatch_factory=lambda components: None,
        pattern_snapshot_builder=_executing_empty_snapshot_builder,
    )
    pattern_job = [
        job
        for job in scheduler.get_jobs()
        if job.id == HOURLY_PATTERN_TICK_JOB_ID
    ][0]

    with caplog.at_level(logging.INFO):
        result = pattern_job.func()

    assert result == []
    assert "pattern_tick_cycle_completed" in caplog.text
    assert "allowed_count=0" in caplog.text
    assert "total_matches=0" in caplog.text
    assert components_factory.engines_created == 1
    assert all(engine.disposed for engine in components_factory.engines)


def test_pattern_tick_disposes_engine_after_each_invocation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression for issue #85: each tick must own and dispose its engine."""
    components_factory = _EnginePerTickComponentsFactory()

    with caplog.at_level(logging.INFO):
        for _ in range(4):
            result = _run_observation_only_pattern_tick_cycle(
                components_factory=components_factory,
                dispatch_factory=lambda components: None,
                snapshot_builder=_executing_empty_snapshot_builder,
            )
            assert result == []

    assert caplog.text.count("pattern_tick_cycle_completed") == 4
    assert components_factory.engines_created == 4
    assert all(engine.disposed for engine in components_factory.engines)
    assert "pattern_tick_cycle_failed" not in caplog.text
    assert "attached to a different loop" not in caplog.text
    assert "AsyncAdaptedQueuePool" not in caplog.text
    assert "engine reused after loop close" not in caplog.text


def test_cached_engine_across_invocations_is_rejected_by_harness() -> None:
    """Verify the harness catches the failure mode that #84 had."""
    components_factory = _CachedEngineComponentsFactory()

    first_result = _run_observation_only_pattern_tick_cycle(
        components_factory=components_factory,
        dispatch_factory=lambda components: None,
        snapshot_builder=_executing_empty_snapshot_builder,
    )
    assert first_result == []

    with pytest.raises(RuntimeError, match="engine reused after loop close detected"):
        _run_observation_only_pattern_tick_cycle(
            components_factory=components_factory,
            dispatch_factory=lambda components: None,
            snapshot_builder=_executing_empty_snapshot_builder,
        )


def test_default_dispatch_factory_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabled Telegram settings should not construct runtime dispatch."""
    monkeypatch.setitem(
        sys.modules,
        "duzman.settings",
        _settings_module(SimpleNamespace(telegram_enabled=False)),
    )

    assert _default_pattern_dispatch_factory(_components_for_engine(_LoopBoundEngine())) is None


def test_default_dispatch_factory_uses_postgresql_dialect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime dispatch composition should pass PostgreSQL dialect explicitly."""
    captured: dict[str, object] = {}

    class _Secret:
        def get_secret_value(self) -> str:
            return "fake-token"

    class _TelegramClient:
        def __init__(self, **kwargs: object) -> None:
            captured["telegram_client"] = kwargs

    class _TelegramSender:
        def __init__(self, **kwargs: object) -> None:
            captured["telegram_sender"] = kwargs

    class _DispatchService:
        def __init__(self, **kwargs: object) -> None:
            captured["dispatch_service"] = kwargs

        async def dispatch_events(self, events: object) -> list[object]:
            return []

    monkeypatch.setitem(
        sys.modules,
        "duzman.settings",
        _settings_module(
            SimpleNamespace(
                telegram_enabled=True,
                telegram_bot_token=_Secret(),
                telegram_chat_id="fake-chat",
                telegram_timeout_ms=5000,
            )
        ),
    )
    monkeypatch.setattr(market_data_scheduler, "TelegramHttpClient", _TelegramClient)
    monkeypatch.setattr(market_data_scheduler, "TelegramBaseSender", _TelegramSender)
    monkeypatch.setattr(market_data_scheduler, "DispatchRuntimeService", _DispatchService)

    dispatcher = _default_pattern_dispatch_factory(_components_for_engine(_LoopBoundEngine()))

    assert dispatcher is not None
    service_kwargs = captured["dispatch_service"]
    assert isinstance(service_kwargs, dict)
    assert service_kwargs["dialect"] == DISPATCH_DELIVERY_DIALECT_POSTGRESQL


def _settings_module(settings: object) -> ModuleType:
    """Build a fake settings module without loading project configuration files."""
    module = ModuleType("duzman.settings")
    module.settings = settings
    return module


async def _executing_empty_snapshot_builder(
    session: AsyncSession,
    assets: list[str],
    now: datetime,
) -> MetricsSnapshot:
    """Touch the shared DB session before returning an empty snapshot."""
    await session.execute(select(1))
    return MetricsSnapshot(
        built_at=now.astimezone(UTC),
        assets={"BTC": AssetMetrics(asset="BTC", values={})},
        global_metrics={
            "fear_greed_index": None,
            "btc_dominance": None,
            "btc_dominance_change_7d_pct": None,
        },
    )


class _EnginePerTickComponentsFactory:
    """Create fresh loop-bound engine components for each pattern tick."""

    def __init__(self) -> None:
        self.engines: list[_LoopBoundEngine] = []

    @property
    def engines_created(self) -> int:
        """Return how many fake engines this factory has created."""
        return len(self.engines)

    def __call__(self) -> AsyncDatabaseSessionComponents:
        """Return a fresh engine and session factory bound to the current loop."""
        engine = _LoopBoundEngine()
        self.engines.append(engine)
        return _components_for_engine(engine)


class _CachedEngineComponentsFactory:
    """Return the same loop-bound engine to simulate PR #84's failure mode."""

    def __init__(self) -> None:
        self.engine = _LoopBoundEngine()

    def __call__(self) -> AsyncDatabaseSessionComponents:
        """Return components backed by one cached engine instance."""
        return _components_for_engine(self.engine)


def _components_for_engine(engine: _LoopBoundEngine) -> AsyncDatabaseSessionComponents:
    """Build test components from one fake loop-bound engine."""

    def session_factory() -> AbstractAsyncContextManager[AsyncSession]:
        return cast(
            AbstractAsyncContextManager[AsyncSession],
            _LoopBoundSessionContext(engine),
        )

    return AsyncDatabaseSessionComponents(
        async_engine=cast(AsyncEngine, engine),
        session_factory=cast(Any, session_factory),
    )


class _LoopBoundEngine:
    """Fake engine that rejects use after disposal across event loops."""

    def __init__(self) -> None:
        self.disposed = False
        self.dispose_calls = 0
        self.loop_id: int | None = None

    def assert_usable_in_current_loop(self) -> None:
        """Raise when a disposed engine is reused by a later invocation."""
        current_loop_id = id(asyncio.get_running_loop())
        if self.disposed:
            raise RuntimeError("engine reused after loop close detected")
        if self.loop_id is None:
            self.loop_id = current_loop_id
            return
        if self.loop_id != current_loop_id:
            raise RuntimeError("attached to a different loop")

    async def dispose(self) -> None:
        """Mark the fake engine disposed."""
        self.dispose_calls += 1
        self.disposed = True


class _LoopBoundSessionContext:
    """Async context manager that yields a fake loop-bound session."""

    def __init__(self, engine: _LoopBoundEngine) -> None:
        self._session = _LoopBoundSession(engine)

    async def __aenter__(self) -> _LoopBoundSession:
        """Return the fake session."""
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Exit the fake session context."""
        return None


class _LoopBoundSession:
    """Fake AsyncSession surface that checks engine loop ownership."""

    def __init__(self, engine: _LoopBoundEngine) -> None:
        self._engine = engine

    async def execute(self, *args: Any, **kwargs: Any) -> object:
        """Execute a statement after asserting engine loop ownership."""
        self._engine.assert_usable_in_current_loop()
        return object()

    async def scalar(self, *args: Any, **kwargs: Any) -> int:
        """Return zero after asserting engine loop ownership."""
        self._engine.assert_usable_in_current_loop()
        return 0
