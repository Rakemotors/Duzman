from collections.abc import AsyncIterator, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import AlertDelivery, PatternTrigger
from duzman.runtime.verify_telegram_base import (
    TelegramBaseSmokeSettings,
    _async_main,
    _build_parser,
    main,
)
from duzman.telegram.sender import TelegramClient
from tests.telegram.test_sender import _create_tables


class FakeTelegramClient:
    """Telegram client test double returning deterministic message ids."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.next_message_id = 321

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Return one deterministic Telegram message id."""
        del chat_id, text, reply_to_message_id
        return self.next_message_id


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an async SQLite session factory for Telegram base smoke tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_telegram_base_creates_sent_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B0 smoke should create a smoke trigger and record Telegram message id."""
    exit_code = await _run_async_main(
        [],
        settings_provider=lambda: TelegramBaseSmokeSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            ai_explanations_enabled=False,
            telegram_bot_token="token",
            telegram_chat_id_alerts="42",
        ),
        session_factory=session_factory,
        telegram_client_factory=FakeTelegramClient,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "TELEGRAM_BASE_SMOKE_OK telegram_message_id=321 trigger_id=" in output


@pytest.mark.asyncio
async def test_verify_telegram_base_persists_trigger_and_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B0 smoke should persist smoke_b0 trigger and sent delivery row."""
    exit_code = await _run_async_main(
        [],
        settings_provider=lambda: TelegramBaseSmokeSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            ai_explanations_enabled=False,
            telegram_bot_token="token",
            telegram_chat_id_alerts="42",
        ),
        session_factory=session_factory,
        telegram_client_factory=FakeTelegramClient,
    )

    async with session_factory() as session:
        trigger = await session.scalar(select(PatternTrigger))
        delivery = await session.scalar(select(AlertDelivery))

    assert exit_code == 0
    assert trigger is not None
    assert trigger.pattern_name == "smoke_b0"
    assert delivery is not None
    assert delivery.status == "sent"
    assert delivery.telegram_message_id == 321


async def _run_async_main(
    argv: list[str],
    *,
    settings_provider: Callable[[], TelegramBaseSmokeSettings],
    session_factory: async_sessionmaker[AsyncSession],
    telegram_client_factory: Callable[[str], TelegramClient],
) -> int:
    """Run the private async entrypoint without nesting asyncio.run in tests."""
    args = _build_parser().parse_args(argv)
    return await _async_main(
        args,
        settings_provider=settings_provider,
        session_factory=session_factory,
        telegram_client_factory=telegram_client_factory,
    )


def test_verify_telegram_base_rejects_enabled_ai(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B0 smoke should refuse to run when AI explanations are enabled."""
    exit_code = main(
        [],
        settings_provider=lambda: TelegramBaseSmokeSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            ai_explanations_enabled=True,
            telegram_bot_token="token",
            telegram_chat_id_alerts="42",
        ),
        session_factory=session_factory,
        telegram_client_factory=FakeTelegramClient,
    )

    assert exit_code == 2
    assert "AI_EXPLANATIONS_ENABLED must be false" in capsys.readouterr().out


def test_verify_telegram_base_rejects_missing_telegram_config(
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B0 smoke should return exit 2 when Telegram config is missing."""
    exit_code = main(
        [],
        settings_provider=lambda: TelegramBaseSmokeSettings(
            database_url="sqlite+aiosqlite:///:memory:",
            ai_explanations_enabled=False,
            telegram_bot_token="",
            telegram_chat_id_alerts="42",
        ),
        session_factory=session_factory,
        telegram_client_factory=FakeTelegramClient,
    )

    assert exit_code == 2
    assert "missing TELEGRAM_BOT_TOKEN" in capsys.readouterr().out
