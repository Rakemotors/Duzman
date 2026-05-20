# src/duzman/ai/prompt_builder.py
# Prompt construction for AI explanations. Builds bounded, deterministic context
# from normalized AlertGate data only.
"""Prompt builder for AlertGate AI explanations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from duzman.db.models import PatternTrigger, PriceSnapshot

SYSTEM_PROMPT = "\n".join(
    [
        "Ты — технический аналитик, объясняющий пользователю, почему сработал "
        "автоматический сигнал на крипторынке.",
        "",
        "Правила:",
        "1. Отвечай на русском языке.",
        "2. НЕ давай торговых инструкций. Запрещены фразы вида \"покупай\", "
        "\"продавай\", \"входи в позицию\", \"шорти\", \"лонгуй\", "
        "\"сейчас хороший момент для входа\".",
        "3. Структура ответа строго в четырёх блоках:",
        "   - Почему сработал сигнал",
        "   - Что усиливает сигнал",
        "   - Что ослабляет сигнал",
        "   - На какие метрики и условия смотреть дальше",
        "4. Кратко, по делу, без hype, без эмодзи, без markdown-заголовков. "
        "Используй обычные строки и абзацы.",
        "5. Не выдумывай данные, которых нет во входном контексте.",
        "6. Если данных недостаточно для одного из четырёх блоков — напиши "
        "\"недостаточно данных\" в этом блоке.",
    ]
)


@dataclass(frozen=True)
class PromptBundle:
    """Bounded prompt payload and deterministic identifiers."""

    system: str
    user: str
    context_json: dict[str, Any]
    prompt_hash: str
    cache_key: str


def build_prompt(
    pattern_trigger: PatternTrigger,
    indicator_values: Mapping[str, Any] | None,
    price_snapshot: Sequence[PriceSnapshot] | PriceSnapshot | None,
    *,
    max_input_chars: int = 6000,
) -> PromptBundle:
    """Build a Russian explanation prompt from normalized AlertGate context."""
    context = _context(pattern_trigger, indicator_values, price_snapshot)
    user = _render_user(context)
    context = _truncate_context(context, max_input_chars=max_input_chars)
    user = _render_user(context)
    prompt_hash = _sha256(SYSTEM_PROMPT + user)
    return PromptBundle(
        system=SYSTEM_PROMPT,
        user=user,
        context_json=context,
        prompt_hash=prompt_hash,
        cache_key=_cache_key(context),
    )


def _context(
    pattern_trigger: PatternTrigger,
    indicator_values: Mapping[str, Any] | None,
    price_snapshot: Sequence[PriceSnapshot] | PriceSnapshot | None,
) -> dict[str, Any]:
    """Return normalized prompt context without raw payload fields."""
    conditions_snapshot = pattern_trigger.conditions_snapshot or {}
    matched_conditions = {
        str(key): _json_safe(value)
        for key, value in sorted(conditions_snapshot.items())
        if key != "gate_decision"
    }
    return {
        "asset": pattern_trigger.asset,
        "pattern_name": pattern_trigger.pattern_name,
        "severity": pattern_trigger.severity,
        "gate_decision": str(conditions_snapshot.get("gate_decision", "UNKNOWN")),
        "matched_conditions": matched_conditions,
        "indicator_values": {
            str(key): _json_safe(value)
            for key, value in sorted((indicator_values or {}).items())
        },
        "price_snapshot": _price_points(price_snapshot),
    }


def _truncate_context(context: dict[str, Any], *, max_input_chars: int) -> dict[str, Any]:
    """Trim price points first, then indicators, until prompt fits."""
    trimmed = dict(context)
    trimmed["price_snapshot"] = list(context["price_snapshot"])
    trimmed["indicator_values"] = dict(context["indicator_values"])
    while len(_render_user(trimmed)) > max_input_chars and trimmed["price_snapshot"]:
        trimmed["price_snapshot"].pop(0)
    while len(_render_user(trimmed)) > max_input_chars and len(trimmed["indicator_values"]) > 1:
        first_key = sorted(trimmed["indicator_values"])[0]
        del trimmed["indicator_values"][first_key]
    return trimmed


def _render_user(context: Mapping[str, Any]) -> str:
    """Render user prompt text from normalized context."""
    lines = [
        f"Актив: {context['asset']}",
        f"Паттерн: {context['pattern_name']}",
        f"Severity: {context['severity']}",
        f"Gate decision: {context['gate_decision']}",
        "Сработавшие условия:",
    ]
    lines.extend(_bullet_lines(context["matched_conditions"]))
    lines.append("")
    lines.append("Текущие индикаторы:")
    lines.extend(_bullet_lines(context["indicator_values"]))
    lines.append("")
    lines.append("Снапшот цены:")
    price_points = context["price_snapshot"]
    if price_points:
        for point in price_points:
            lines.append(f"- {point['ts']}: {point['price_usd']}")
    else:
        lines.append("- недостаточно данных")
    return "\n".join(lines)


def _bullet_lines(values: Mapping[str, Any]) -> list[str]:
    """Render a mapping as deterministic prompt bullets."""
    if not values:
        return ["- недостаточно данных"]
    return [f"- {key}: {value}" for key, value in sorted(values.items())]


def _price_points(
    price_snapshot: Sequence[PriceSnapshot] | PriceSnapshot | None,
) -> list[dict[str, Any]]:
    """Return bounded price points without raw payload."""
    if price_snapshot is None:
        return []
    snapshots = (
        [price_snapshot]
        if isinstance(price_snapshot, PriceSnapshot)
        else list(price_snapshot)
    )
    points = [
        {
            "ts": snapshot.ts.isoformat(),
            "price_usd": str(snapshot.price_usd),
        }
        for snapshot in snapshots[-6:]
    ]
    return points


def _cache_key(context: Mapping[str, Any]) -> str:
    """Return the day-8 cache key derived from normalized reason names."""
    reason = "|".join(sorted(str(key) for key in context["matched_conditions"]))
    return _sha256(
        f"{context['asset']}|{context['pattern_name']}|"
        f"{context['severity']}|{context['gate_decision']}|{reason}"
    )


def _sha256(value: str) -> str:
    """Return a hex SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:64]


def _json_safe(value: Any) -> Any:
    """Convert common non-JSON scalar values into safe prompt values."""
    if isinstance(value, Decimal):
        return str(value)
    return value


def context_json_size(context: Mapping[str, Any]) -> int:
    """Return serialized context size in UTF-8 characters."""
    return len(json.dumps(context, ensure_ascii=False, sort_keys=True))
