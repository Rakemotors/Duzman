# Spec: pattern_evaluation_engine

## Контекст
Третий модуль Pattern Engine (день 6 ТЗ v1.4, раздел 7.7).
Спека 1 загрузила определения шаблонов из config/patterns.yaml в
pydantic-модели (src/duzman/patterns/config.py, models.py).
Спека 2 построила MetricsSnapshot со значениями метрик per-asset и
global (src/duzman/patterns/snapshot.py).

Этот модуль берёт загруженные шаблоны и снапшот, прогоняет шаблоны
по применимым активам, и возвращает список сработавших триггеров.

Этот модуль НЕ принимает решение об отправке в Telegram (Спека 4).
НЕ пишет в БД (Спека 4). НЕ запускается из scheduler (Спека 5).
Только чистая функция: (patterns, snapshot) -> list[PatternMatch].

## Цель
Иметь функцию evaluate_patterns(patterns, snapshot) -> list[PatternMatch],
которая для каждого шаблона из patterns и каждого asset из
snapshot.assets, входящего в pattern.applies_to, проверяет условия
шаблона и возвращает список совпадений с полным snapshot значений
метрик, использованных в условиях.

## Входы
- patterns: list[Pattern] — результат load_patterns() из Спеки 1
- snapshot: MetricsSnapshot — результат build_snapshot() из Спеки 2

## Выходы

Новый файл src/duzman/patterns/evaluation.py:

1. Pydantic v2 модель PatternMatch:

       class PatternMatch(BaseModel):
           pattern_name: str
           asset: str
           severity: str
           evaluated_at: datetime
           conditions_snapshot: dict[str, float | int]
           model_config = ConfigDict(extra="forbid", frozen=True)

   conditions_snapshot содержит ТОЛЬКО метрики, которые
   фигурировали в условиях этого шаблона (не весь snapshot).
   Если в условиях были global метрики (fear_greed_index,
   btc_dominance) — они тоже идут в conditions_snapshot.
   evaluated_at = snapshot.built_at.

2. Функция evaluate_patterns(
       patterns: list[Pattern],
       snapshot: MetricsSnapshot,
   ) -> list[PatternMatch]

   - Sync функция (не async, в БД не ходит)
   - Порядок выхода: стабильный, по (pattern.name, asset) в
     лексикографическом порядке
   - Шаблон НЕ срабатывает на активе если:
     a) asset не в pattern.applies_to
     b) хотя бы одна метрика из условий шаблона = None в snapshot
        (метрика недоступна — не срабатываем; см. раздел "Семантика None")
     c) хотя бы одно условие не выполнено
   - Если все условия выполнены — добавляется PatternMatch с
     conditions_snapshot из реальных значений метрик

3. Внутренние функции:
   _evaluate_pattern_for_asset(pattern, asset, snapshot) -> PatternMatch | None
   _evaluate_condition_group(group, metric_values) -> bool
   _evaluate_single_condition(condition, metric_values, asset) -> bool
   _resolve_metric_value(metric_name, asset, snapshot) -> float | int | None
   _resolve_threshold(condition, asset) -> float | int | None

## Семантика

Шаблоны имеют структуру (из Спеки 1):

    Pattern:
      name: str
      display_name: str
      severity: "INFO" | "WARNING" | "CRITICAL"
      applies_to: list[str]
      cooldown_hours: int
      conditions: ConditionGroup

    ConditionGroup:
      all: list[Condition | ConditionGroup] | None
      any: list[Condition | ConditionGroup] | None

    Condition:
      metric: str
      operator: ">" | "<" | ">=" | "<=" | "==" | "!="
      value: float | int | None
      per_asset_thresholds: dict[str, float | int] | None

Точные имена полей сверь по src/duzman/patterns/models.py
(этот файл создан Спекой 1, опирайся на него как на источник правды).

Семантика операторов:
- LHS = snapshot value для метрики
- RHS = condition.value, либо per_asset_thresholds[asset] если задан
- Числовое сравнение float-ами

Семантика None:
- Если LHS = None (метрика не собрана / неприменима / расчёт упал) —
  условие считается невыполненным. Шаблон НЕ срабатывает.
- Если RHS = None (нет ни value, ни per_asset_thresholds[asset]
  для данного актива) — это конфигурационная ошибка. Логировать
  log_event "pattern_misconfigured" с pattern_name, asset, metric_name
  и считать условие невыполненным. Не падать.

Семантика per_asset_thresholds:
- Если condition.per_asset_thresholds задан И в нём есть ключ для
  текущего asset — используется это значение
- Если condition.per_asset_thresholds задан но для asset ключа нет —
  это конфигурационная ошибка (см. семантику None для RHS)
- Если condition.per_asset_thresholds не задан — используется
  condition.value
- Если задано и то и другое — per_asset_thresholds имеет приоритет

Семантика global метрик в условиях:
- Если метрика в условии входит в GLOBAL_METRICS (fear_greed_index,
  btc_dominance, btc_dominance_change_7d_pct) — значение читается
  из snapshot.global_metrics
- Иначе — из snapshot.assets[asset].values

Семантика ConditionGroup:
- group.all = AND по всем элементам
- group.any = OR по всем элементам
- Если в шаблоне условия = ConditionGroup(all=[...]) — все должны
  быть истинны
- Поддержать вложенность (Condition внутри all внутри all и т.д.)
- В текущих 10 шаблонах ТЗ Приложение А используется только all
  плоского уровня, но движок должен корректно обрабатывать вложенные
  группы для будущих шаблонов

## Требования
- Pure-функциональный модуль, без БД, без I/O, без логов кроме
  pattern_misconfigured
- Никаких импортов из src/duzman/collectors/, db/repositories/, api/,
  scheduler/
- Можно импортировать: src/duzman/patterns/models.py,
  src/duzman/patterns/snapshot.py (для типа MetricsSnapshot),
  src/duzman/patterns/known_metrics.py, duzman.logging_config
- Все datetime — UTC aware
- structlog: log_event "pattern_misconfigured" с level=WARNING
- При исключении внутри одного шаблона — НЕ ронять весь evaluate_patterns.
  Шаблон считается не сработавшим, log_event "pattern_evaluation_failed"
  с pattern_name, asset, error. Остальные шаблоны продолжают
- Конвенции проекта: docstrings, snake_case, src-layout

## Тесты

tests/unit/patterns/test_evaluation.py — pytest, sync (asyncio не нужен).
Создаются in-memory объекты Pattern и MetricsSnapshot, без БД.

Покрытие, минимум 18 тестов:

1. test_no_patterns_returns_empty_list
2. test_pattern_not_in_applies_to_skipped — шаблон для BTC, asset=SOL
3. test_simple_all_match — все условия выполнены, шаблон срабатывает
4. test_simple_all_one_fails — одно условие не выполнено, не срабатывает
5. test_operator_gt
6. test_operator_lt
7. test_operator_gte
8. test_operator_lte
9. test_operator_eq
10. test_operator_neq
11. test_none_metric_blocks_match — LHS=None, шаблон не срабатывает
12. test_per_asset_threshold_used — per_asset_thresholds[BTC]=1e9,
    BTC значение 2e9 > 1e9, срабатывает
13. test_per_asset_threshold_missing_key_logs_misconfigured —
    per_asset_thresholds задан, asset=SOL, ключа SOL нет,
    log "pattern_misconfigured", не срабатывает
14. test_global_metric_read_from_global — условие на fear_greed_index,
    значение в snapshot.global_metrics, не в assets
15. test_conditions_snapshot_contains_only_used_metrics — в шаблоне
    2 условия, в conditions_snapshot ровно 2 ключа с реальными
    значениями (не весь snapshot)
16. test_evaluated_at_equals_snapshot_built_at
17. test_severity_propagated_from_pattern
18. test_two_patterns_two_assets_stable_order — 2 шаблона по
    BTC и SOL, проверка лексикографической сортировки результата
19. test_critical_pattern_can_match — severity=CRITICAL
20. test_one_pattern_exception_does_not_break_others — мок одного
    шаблона бросает Exception в _evaluate_pattern_for_asset,
    остальные продолжают; в логе "pattern_evaluation_failed"
21. test_nested_all_groups — вложенный all внутри all, проверка
    рекурсивного вычисления

Минимум 18, рекомендую все 21.

## Критерии готовности
- Все тесты зелёные (222 + минимум 18 новых = 240+)
- src/duzman/patterns/evaluation.py создан
- ARCHITECTURE.md обновлён: новый под-раздел
  "Pattern Engine — Evaluation Layer" с описанием PatternMatch,
  семантики None, per_asset_thresholds, ConditionGroup
- Один commit: feat(patterns): pattern evaluation engine
- git push НЕ делать (Operator пушит вручную)

## Что НЕ делать
- Не реализовывать AlertGate / cooldown (Спека 4)
- Не интегрировать в scheduler (Спека 5)
- Не писать в pattern_triggers (Спека 4)
- Не добавлять новые миграции
- Не делать git push

## Источник правды
- ТЗ: docs/TZ.md v1.4, особенно раздел 4 и Приложение А
- Конвенции: AGENTS.md
- Whitelist метрик: src/duzman/patterns/known_metrics.py
- Модели шаблонов: src/duzman/patterns/models.py
- Снапшот: src/duzman/patterns/snapshot.py
