from datetime import UTC, datetime
from decimal import Decimal

from duzman.ai.prompt_builder import build_prompt, context_json_size
from duzman.db.models import PatternTrigger, PriceSnapshot


def test_build_prompt_renders_required_sections() -> None:
    """Prompt builder should render the day-8 structured user message."""
    bundle = build_prompt(
        _trigger(),
        {"RSI(14) 4h": Decimal("27.3"), "Stoch K": Decimal("18.4")},
        [_price("67120"), _price("65550")],
    )

    assert bundle.system.startswith("Ты — технический аналитик")
    assert "Актив: BTC" in bundle.user
    assert "Паттерн: RSI_oversold_4h" in bundle.user
    assert "Сработавшие условия:" in bundle.user
    assert "Текущие индикаторы:" in bundle.user
    assert "Снапшот цены:" in bundle.user
    assert "raw_payload" not in bundle.user


def test_cache_key_is_deterministic_and_ignores_numeric_values() -> None:
    """Same reason names with different numeric values should share cache key."""
    first = build_prompt(_trigger(rsi=27.3), {"RSI": 27.3}, None)
    second = build_prompt(_trigger(rsi=19.0), {"RSI": 19.0}, None)

    assert first.cache_key == second.cache_key
    assert first.prompt_hash != second.prompt_hash


def test_build_prompt_truncates_price_points_before_indicators() -> None:
    """Long prompts should drop price points first while keeping indicator context."""
    prices = [_price(str(index)) for index in range(12)]
    bundle = build_prompt(
        _trigger(),
        {"zz_indicator": "x" * 120, "aa_indicator": "y" * 120},
        prices,
        max_input_chars=260,
    )

    assert context_json_size(bundle.context_json) > 0
    assert len(bundle.context_json["price_snapshot"]) < 6
    assert bundle.context_json["indicator_values"]


def _trigger(*, rsi: float = 27.3) -> PatternTrigger:
    """Build a minimal PatternTrigger for prompt tests."""
    return PatternTrigger(
        id=1,
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        pattern_name="RSI_oversold_4h",
        asset="BTC",
        severity="medium",
        conditions_snapshot={"gate_decision": "ALLOW", "RSI(14) 4h": rsi},
        alert_sent=False,
    )


def _price(price: str) -> PriceSnapshot:
    """Build a minimal PriceSnapshot for prompt tests."""
    return PriceSnapshot(
        source="binance",
        asset="BTC",
        quote_currency="USDT",
        price_usd=Decimal(price),
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    )
