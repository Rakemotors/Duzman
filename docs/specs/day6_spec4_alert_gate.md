# Spec — day 6 spec 4: AlertGate

## Контекст

День 6 Pattern Engine, спека 4 из 5. Спеки 1-3 завершены (a3fbca8): pattern_config_loader (config.py + models.py с PatternDefinition), metrics_snapshot_builder, pattern_evaluation_engine. Pattern evaluation engine возвращает список Trigger-объектов (срабатывания шаблонов). Эта спека вводит AlertGate — слой между evaluation engine и записью в БД, который для каждого Trigger принимает решение ALLOW или одно из SUPPRESS_* в соответствии с TZ v1.6 раздел 4.6. На дне 6 физическая отправка в Telegram не реализуется — AlertGate сохраняет своё решение в pattern_triggers.conditions_snapshot.gate_decision как временный источник правды для счётчиков. Дефолт cooldown_hours = 2 часа уже реализован в Pydantic-модели PatternDefinition (src/duzman/patterns/models.py, поле с default=2.0), AlertGate собственного fallback не имеет.

Канонический ТЗ — v1.6: https://gist.github.com/Rakemotors/d64749d7920037be9a218586b7a10fcb

Состояние репо: origin/main = 3267be4, 243 теста зелёные, pattern_triggers уже в схеме (initial_schema b009e25bfab4).

## Цель

Реализовать AlertGate как pure-функцию принятия решения над снапшотом счётчиков и Trigger-объектом, плюс репозиторий для записи pattern_triggers и подсчёта ALLOW в окнах (час, сутки, cooldown per dedup_key). На дне 6 Telegram не вызывается. alert_sent остаётся FALSE. gate_decision записывается в conditions_snapshot.

## Входы

- Trigger (dataclass из спеки 3): pattern_name, asset, severity (WARNING/INFO/CRITICAL), conditions_snapshot (dict со значениями метрик), ts (datetime UTC, момент evaluation)
- PatternDefinition (из src/duzman/patterns/models.py): cooldown_hours (float, уже заполнен Pydantic-дефолтом 2.0 если поле отсутствовало в YAML)
- Состояние таблицы pattern_triggers за окно (час UTC, сутки UTC, cooldown окно per dedup_key)
- AsyncSession SQLAlchemy

## Выходы

- src/duzman/patterns/alert_gate.py
  - enum GateDecision(str, Enum) с пятью значениями: ALLOW = "ALLOW", SUPPRESS_COOLDOWN = "SUPPRESS_COOLDOWN", SUPPRESS_SOFT_CAP = "SUPPRESS_SOFT_CAP", SUPPRESS_HARD_CAP_HOUR = "SUPPRESS_HARD_CAP_HOUR", SUPPRESS_HARD_CAP_DAY = "SUPPRESS_HARD_CAP_DAY"
  - class AlertGate:
    - конструктор принимает PatternTriggerRepository
    - async def evaluate(self, trigger, pattern_definition: PatternDefinition, session: AsyncSession) -> GateDecision
    - метод вызывает repository для получения данных счётчиков, применяет порядок проверок и возвращает GateDecision

- src/duzman/db/repositories/pattern_trigger_repository.py
  - class PatternTriggerRepository:
    - async def count_allow_in_window(self, session, window_start: datetime, window_end: datetime) -> int
    - async def cooldown_hit(self, session, pattern_name: str, asset: str, cooldown_window_start: datetime, now: datetime) -> bool
    - async def insert_trigger(self, session, trigger, gate_decision: GateDecision) -> int (возвращает id записанной строки)
  - insert_trigger:
    - копирует trigger.conditions_snapshot в новый dict (чтобы не мутировать оригинал)
    - добавляет ключ "gate_decision" со значением gate_decision.value (строка)
    - пишет в pattern_triggers: ts, pattern_name, asset, severity, conditions_snapshot, alert_sent=FALSE
    - НЕ заполняет ai_explanation (день 7)
    - commit делает caller, не репозиторий

- tests/patterns/test_alert_gate.py — минимум 9 тестов (5 базовых на каждое значение GateDecision + 1 на bypass CRITICAL над soft cap + 3 на порядок проверок)
- tests/db/test_pattern_trigger_repository.py — отдельный модуль на репозиторий (insert + два counter-метода, минимум 5 тестов)

## Требования

Порядок проверок в AlertGate.evaluate (строго, реализовать именно в этой последовательности):

1. cooldown — repository.cooldown_hit(pattern_name=trigger.pattern_name, asset=trigger.asset, cooldown_window_start = trigger.ts - timedelta(hours=pattern_definition.cooldown_hours), now=trigger.ts). Если True — вернуть SUPPRESS_COOLDOWN
2. daily hard cap — repository.count_allow_in_window(window_start = floor_to_day_utc(trigger.ts), window_end = trigger.ts). Сохранить значение в локальную переменную daily_count. Если daily_count >= 30 — вернуть SUPPRESS_HARD_CAP_DAY
3. hourly hard cap — repository.count_allow_in_window(window_start = floor_to_hour_utc(trigger.ts), window_end = trigger.ts). Сохранить в локальную переменную hourly_count. Если hourly_count >= 10 — вернуть SUPPRESS_HARD_CAP_HOUR
4. soft cap — использовать ту же hourly_count из шага 3 (НЕ запрашивать БД повторно). Если hourly_count >= 3 И trigger.severity != "CRITICAL" — вернуть SUPPRESS_SOFT_CAP
5. Иначе — ALLOW

CRITICAL обходит ТОЛЬКО soft cap (шаг 4), но подчиняется cooldown и обоим hard cap.

Cooldown:
- cooldown_hours берётся из pattern_definition.cooldown_hours (Pydantic уже подставил дефолт 2.0 если YAML не содержал поля, AlertGate fallback не делает)
- cooldown окно: [trigger.ts - timedelta(hours=cooldown_hours), trigger.ts)
- cooldown_hit считает только записи с gate_decision = 'ALLOW' в этом окне по тому же pattern_name + asset

count_allow_in_window реализация (Postgres):
- SQL: SELECT COUNT(*) FROM pattern_triggers WHERE ts >= :window_start AND ts < :window_end AND conditions_snapshot->>'gate_decision' = 'ALLOW'
- глобальный счётчик, не per pattern/asset

cooldown_hit реализация (Postgres):
- SQL: SELECT 1 FROM pattern_triggers WHERE pattern_name = :pn AND asset = :asset AND ts >= :window_start AND ts < :now AND conditions_snapshot->>'gate_decision' = 'ALLOW' LIMIT 1
- возвращает True если найдена хотя бы одна запись

Окна UTC (вспомогательные функции в alert_gate.py, не экспортировать):
- floor_to_hour_utc(ts): datetime(ts.year, ts.month, ts.day, ts.hour, 0, 0, tzinfo=timezone.utc)
- floor_to_day_utc(ts): datetime(ts.year, ts.month, ts.day, 0, 0, 0, tzinfo=timezone.utc)
- ts на входе всегда timezone-aware UTC; если придёт naive — assert + AssertionError с понятным сообщением

Что НЕ делать:
- никакого Telegram-вызова, никакого alerts_sent (день 7)
- никакой записи sweep-message "N suppressed" (день 7)
- никакой миграции — pattern_triggers уже в initial_schema
- не считать suppress-решения в счётчики
- НЕ запрашивать count для одного и того же окна дважды (hourly count переиспользуется для soft cap)
- НЕ делать собственный fallback по cooldown в AlertGate — дефолт живёт в PatternDefinition

AlertGate.evaluate сам НЕ пишет в БД. Запись делает caller (scheduler integration в спеке 5) через repository.insert_trigger после получения решения. Это разделение нужно для тестируемости gate без БД.

Стиль:
- docstring на каждом классе и публичном методе (см. AGENTS.md / .claude/skills/duzman-conventions/SKILL.md, секция документации)
- комментарий-заголовок в начале каждого нового файла (как в config.py)
- type hints везде, включая возврат
- async/await через SQLAlchemy AsyncSession
- никаких sync обёрток, никакого asyncio.run

Dialect-agnostic SQL:

В Postgres используется оператор ->>. В тестах SQLite (aiosqlite) не понимает ->>, нужен func.json_extract(col, '$.path'). Решение: в репозитории детектировать диалект через session.get_bind().dialect.name и собирать ColumnElement соответственно.

    # Пример реализации в репозитории:
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession
    from duzman.db.models import PatternTrigger

    def _gate_decision_expr(dialect_name: str):
        if dialect_name == "sqlite":
            return func.json_extract(
                PatternTrigger.conditions_snapshot, "$.gate_decision"
            )
        # Postgres и совместимые
        return PatternTrigger.conditions_snapshot.op("->>")("gate_decision")

dialect_name достать так:

    bind = session.get_bind()
    dialect_name = bind.dialect.name  # 'postgresql' или 'sqlite'

Тесты:

tests/patterns/test_alert_gate.py — gate в изоляции, repository замокан через unittest.mock.AsyncMock. Никакой БД, никаких реальных сессий. Trigger собирается фикстурой.

Минимальный набор:

- test_allow_when_no_constraints_hit — cooldown_hit=False, hourly=0, daily=0, severity=WARNING -> ALLOW
- test_suppress_cooldown — cooldown_hit=True, severity=WARNING -> SUPPRESS_COOLDOWN
- test_suppress_cooldown_even_for_critical — cooldown_hit=True, severity=CRITICAL -> SUPPRESS_COOLDOWN (CRITICAL не обходит cooldown)
- test_suppress_hard_cap_day — cooldown_hit=False, daily_count=30, severity=CRITICAL -> SUPPRESS_HARD_CAP_DAY (CRITICAL не обходит day hard cap)
- test_suppress_hard_cap_hour — cooldown_hit=False, daily_count=10, hourly_count=10, severity=CRITICAL -> SUPPRESS_HARD_CAP_HOUR
- test_suppress_soft_cap — cooldown_hit=False, daily_count=3, hourly_count=3, severity=WARNING -> SUPPRESS_SOFT_CAP
- test_critical_bypasses_soft_cap — cooldown_hit=False, daily_count=3, hourly_count=3, severity=CRITICAL -> ALLOW
- test_order_cooldown_beats_hard_cap_day — cooldown_hit=True И daily_count=30 -> SUPPRESS_COOLDOWN (cooldown первый)
- test_order_hard_cap_day_beats_hard_cap_hour — daily=30 И hourly=10 -> SUPPRESS_HARD_CAP_DAY
- test_order_hard_cap_hour_beats_soft_cap — hourly=10, severity=WARNING -> SUPPRESS_HARD_CAP_HOUR (не soft cap)

Дополнительно:

- test_hourly_count_not_requeried — проверить через AsyncMock.call_count что count_allow_in_window вызвался не более 2 раз (один на daily, один на hourly), не три

tests/db/test_pattern_trigger_repository.py — async SQLite через aiosqlite + AsyncSession. Использовать существующие fixtures из tests/db (если есть session-фикстура — её; если нет — создать локальную). Минимальный набор:

- test_insert_trigger_writes_gate_decision — insert(trigger, ALLOW), затем SELECT по id, проверить:
  - conditions_snapshot["gate_decision"] == "ALLOW"
  - alert_sent == False
  - ai_explanation is None
  - pattern_name, asset, severity, ts равны входным
- test_insert_trigger_does_not_mutate_input_snapshot — передать trigger со снапшотом {"rsi": 70}, проверить что после insert исходный dict не содержит "gate_decision"
- test_count_allow_in_window_counts_only_allow — вставить 2 ALLOW + 3 SUPPRESS_COOLDOWN в окне, count_allow_in_window вернёт 2
- test_count_allow_in_window_respects_boundaries — три записи на ts = window_start, ts = (window_start + window_end)/2, ts = window_end. Count должен вернуть 2 (включая window_start, исключая window_end)
- test_cooldown_hit_matches_pattern_and_asset — вставить ALLOW по (patternA, BTC). Проверить:
  - cooldown_hit(patternA, BTC) == True
  - cooldown_hit(patternA, ETH) == False
  - cooldown_hit(patternB, BTC) == False
- test_cooldown_hit_only_allow — вставить SUPPRESS_COOLDOWN по (patternA, BTC), cooldown_hit вернёт False

## Критерии готовности

- pytest -q проходит без ошибок: 243 предыдущих теста + новые тесты этой спеки (минимум 16 новых) зелёные
- alert_gate.py содержит enum GateDecision с пятью значениями и класс AlertGate с методом evaluate
- pattern_trigger_repository.py содержит класс PatternTriggerRepository с методами insert_trigger, count_allow_in_window, cooldown_hit
- ARCHITECTURE.md обновлён: в разделе про pattern engine добавлен абзац про AlertGate, его место между evaluation engine и БД, и про то что физическая отправка в Telegram остаётся на день 7
- conditions_snapshot после insert содержит ключ gate_decision со значением одного из пяти строковых значений enum
- alert_sent после insert на дне 6 равен FALSE
- никакого Telegram-кода, никакой alerts_sent-таблицы, никаких миграций
- AlertGate.evaluate использует ровно до 3 запросов к репозиторию в худшем случае: один cooldown_hit, два count_allow_in_window (daily, hourly). Для soft cap БД повторно не запрашивается
- репо-методы покрыты в test_pattern_trigger_repository.py через aiosqlite AsyncSession
- gate-логика покрыта в test_alert_gate.py через AsyncMock без БД
- docstrings + file-header comment во всех новых файлах
- git commit с осмысленным message, формат как в предыдущих спеках дня 6
- НЕ делать git push (запрещён по requirements.toml)
