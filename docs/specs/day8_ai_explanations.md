# Day 8 — AI Explanations через Anthropic API

Версия: 1.0
Статус: ready for implementation
Базируется на: TZ v1.7, day7 Telegram MVP (main eb829f0, alembic head d7e1f2a3b4c5)
Формат: Appendix G (spec-driven)

## 1. Контекст и цель

После закрытия day7 Telegram-доставка работает: pattern_triggers → AlertGate → Telegram. Day 8 добавляет опциональный enrichment-слой: после успешной доставки base alert в Telegram, отдельный async-воркер дёргает Anthropic Messages API и присылает в тот же чат второе сообщение с AI-объяснением сигнала (почему сработал, что усиливает, что ослабляет, какие метрики смотреть).

Главный принцип: AI explanations — НЕ блокирующий слой. AlertGate и Telegram delivery работают независимо от состояния Anthropic API. При полном отключении AI (AI_EXPLANATIONS_ENABLED=false) поведение day7 идентично bit-for-bit.

## 2. Scope

In scope:
- Новая таблица alert_explanations.
- Тонкий клиент Anthropic Messages API (только text input/output, без streaming, без tool use).
- Prompt builder с фиксированным форматом и Russian output.
- Background polling worker внутри основного процесса duzman.
- Cache одинаковых объяснений в коротком окне.
- Hard cost caps per-hour и per-day.
- Отправка второго сообщения в Telegram с reply_to_message_id.
- Graceful behaviour при ENABLED=true без ключа.
- Crash recovery через failed_stale.

Out of scope (future work):
- История похожих срабатываний в промпте.
- Edit исходного Telegram-сообщения.
- Multi-channel delivery (только Telegram).
- Streaming responses.
- Tool use / extended thinking.
- UI для просмотра/редактирования объяснений.
- Тонкая бухгалтерия failed_after_api_call как отдельного статуса.

## 3. Конфигурация

Все переменные читаются через существующий Settings (pydantic-settings), добавляются в .env.example.

| Переменная | Тип | Default | Назначение |
|---|---|---|---|
| AI_EXPLANATIONS_ENABLED | bool | false | Главный feature flag. При false весь слой отключён. |
| ANTHROPIC_API_KEY | str | None | Required только при ENABLED=true. Никогда не логируется. |
| AI_EXPLANATION_MODEL | str | claude-sonnet-4-6 | Primary model. |
| AI_EXPLANATION_FALLBACK_MODEL | str | claude-sonnet-4-5-20250929 | Используется при ошибке primary один раз в рамках одного explanation task. |
| AI_EXPLANATION_MAX_PER_HOUR | int | 10 | Hard cap, см. §8. |
| AI_EXPLANATION_MAX_PER_DAY | int | 50 | Hard cap, см. §8. |
| AI_EXPLANATION_TIMEOUT_SECONDS | int | 20 | Per-request timeout на Anthropic call. |
| AI_EXPLANATION_MAX_INPUT_CHARS | int | 6000 | Truncation лимит на собранный prompt context. |
| AI_EXPLANATION_MAX_OUTPUT_TOKENS | int | 500 | max_tokens в Messages API. |
| AI_EXPLANATION_CACHE_WINDOW_MINUTES | int | 15 | Окно для cache lookup. |
| AI_EXPLANATION_WORKER_POLL_SECONDS | int | 30 | Период опроса pending tasks. |
| AI_EXPLANATION_RUNNING_STALE_MINUTES | int | 10 | Порог для failed_stale. |
| AI_EXPLANATION_RETRY_MAX | int | 1 | Максимум retry внутри одного task (fallback model считается этим retry). |

Guard для Codex: Opus-class модели (claude-opus-*) запрещены для day 8 MVP. Если AI_EXPLANATION_MODEL начинается с "claude-opus", Settings валидация падает на старте с явным сообщением.

Расчёт бюджета на дефолтах (информационно):
- ~1500 input tokens + 500 output tokens на один call
- стоимость: (1500/1_000_000)×$3 + (500/1_000_000)×$15 ≈ $0.012 за call
- worst-case 50 calls/день × 30 дней ≈ $18/мес

## 4. Модель данных

### 4.1 Новая таблица alert_explanations

DDL (SQL):

    CREATE TABLE alert_explanations (
        id BIGSERIAL PRIMARY KEY,
        pattern_trigger_id BIGINT NOT NULL REFERENCES pattern_triggers(id) ON DELETE CASCADE,
        alert_delivery_id BIGINT NULL REFERENCES alert_deliveries(id) ON DELETE SET NULL,
        status VARCHAR(32) NOT NULL,
        model VARCHAR(64) NULL,
        cache_key VARCHAR(64) NOT NULL,
        prompt_hash VARCHAR(64) NOT NULL,
        prompt_context_json JSONB NULL,
        prompt_tokens INTEGER NULL,
        completion_tokens INTEGER NULL,
        total_tokens INTEGER NULL,
        text TEXT NULL,
        error_message TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at TIMESTAMPTZ NULL,
        completed_at TIMESTAMPTZ NULL
    );

    CREATE UNIQUE INDEX uq_alert_explanations_pattern_trigger_id
        ON alert_explanations(pattern_trigger_id);

    CREATE INDEX ix_alert_explanations_status_created_at
        ON alert_explanations(status, created_at);

    CREATE INDEX ix_alert_explanations_cache_key_created_at
        ON alert_explanations(cache_key, created_at DESC);

Допустимые значения status:
- pending — task создан, ждёт воркера
- running — воркер взял в работу
- completed — Anthropic вернул ответ, text сохранён
- reused_cache — explanation взят из кэша, Anthropic НЕ дёргался
- skipped_cost_cap — попал под per-hour/per-day лимит, Anthropic НЕ дёргался
- skipped_disabled — создан при ENABLED=true но без ключа (не должно происходить если §6 соблюдён, оставлен как defensive)
- failed — Anthropic вернул ошибку или таймаут после всех retry
- failed_stale — running висел дольше AI_EXPLANATION_RUNNING_STALE_MINUTES

Семантика prompt_context_json: bounded JSON (≤ AI_EXPLANATION_MAX_INPUT_CHARS байт после сериализации) с нормализованным контекстом, без secrets, без raw_payload. Используется для debug.

### 4.2 Alembic миграция

Новая ревизия от d7e1f2a3b4c5. Имя: 8f3a2c1b9d6e_add_alert_explanations.py. Содержит upgrade (CREATE TABLE + индексы) и downgrade (DROP TABLE). Downgrade чистый, проверяется в dev.

Codex deny-rule на alembic upgrade и alembic downgrade в .codex/requirements.toml остаётся в силе. Применение миграции — ручное, Оператором, в dev и prod отдельно.

## 5. Модули

Все новые файлы под duzman/ai/.

### 5.1 duzman/ai/__init__.py

Пустой или с минимальным __all__.

### 5.2 duzman/ai/anthropic_client.py

Тонкая обёртка над Anthropic SDK (официальный пакет anthropic из pyproject.toml).
- Класс AnthropicClient с методом async def create_message(model, system, user, max_tokens, timeout) -> ExplanationResult.
- ExplanationResult: dataclass с полями text, model_used, input_tokens, output_tokens, total_tokens.
- Внутри: один retry с экспоненциальным backoff (0.5s). Retry считается AI_EXPLANATION_RETRY_MAX. Если primary упал — второй вызов идёт на fallback model.
- Маппинг ошибок: ConnectionError, TimeoutError, APIStatusError → AnthropicCallError(reason, retryable).
- API key читается из Settings, никогда не пишется в логи, в repr() замаскирован.

### 5.3 duzman/ai/prompt_builder.py

Чистая функция build_prompt(pattern_trigger, indicator_values, price_snapshot) -> PromptBundle.
- PromptBundle: system, user, context_json, prompt_hash, cache_key.
- system: фиксированная строка из §7.
- user: структурированный текст с asset, pattern_name, severity, gate_decision, matched_conditions, indicator_values, price_snapshot.
- Truncation: если итоговый prompt > AI_EXPLANATION_MAX_INPUT_CHARS, сначала режется price_snapshot, потом indicator_values до минимума.
- prompt_hash: sha256(system + user).
- cache_key: см. §7.

### 5.4 duzman/ai/cost_limiter.py

- async def check_budget(session) -> BudgetStatus.
- BudgetStatus: enum (OK, EXCEEDED_HOUR, EXCEEDED_DAY).
- Источник правды: COUNT(*) FROM alert_explanations WHERE status IN ('running','completed','failed','failed_stale') AND created_at > now() - interval.
- skipped_cost_cap и reused_cache в счёт НЕ входят.

### 5.5 duzman/ai/cache.py

- async def lookup_cached_explanation(session, cache_key) -> Optional[CachedExplanation].
- Возвращает text последней completed или reused_cache записи с тем же cache_key за последние AI_EXPLANATION_CACHE_WINDOW_MINUTES.

### 5.6 duzman/ai/explanation_service.py

Главный оркестратор для одного explanation task. async def process_task(session, explanation_id):
1. SELECT ... FOR UPDATE SKIP LOCKED, claim row, перевод в running, started_at=now().
2. Cache lookup. Если найден — status=reused_cache, text копируется, return.
3. check_budget. Если EXCEEDED_* — status=skipped_cost_cap, return.
4. build_prompt из pattern_trigger context (загруженного отдельным запросом).
5. AnthropicClient.create_message с timeout.
6. На успех: status=completed, text, model, tokens, completed_at=now().
7. На исключение: status=failed, error_message (без secrets), completed_at=now().
8. После completed или reused_cache — вызов telegram_sender.send_explanation(alert_delivery_id, text).

### 5.7 duzman/ai/explanation_worker.py

- class ExplanationWorker, метод async def run_forever().
- В цикле раз в AI_EXPLANATION_WORKER_POLL_SECONDS:
  - reclaim stale: UPDATE ... SET status='failed_stale', error_message='running exceeded N minutes' WHERE status='running' AND started_at < now() - interval.
  - fetch up to N pending ids (N=5 для MVP), обработка последовательно (не параллельно для MVP, проще отлаживать).
- Запускается из главного entrypoint duzman при AI_EXPLANATIONS_ENABLED=true и наличии ANTHROPIC_API_KEY.
- При AI_EXPLANATIONS_ENABLED=true и пустом ключе — лог WARNING один раз, воркер НЕ стартует.

### 5.8 duzman/telegram/sender.py — расширение

- Новый метод async def send_explanation(alert_delivery_id, text).
- Загружает alert_deliveries по id, проверяет наличие message_id.
- Если message_id есть — отправляет новое сообщение в тот же chat_id с reply_to_message_id=message_id.
- Префикс текста: "🤖 Объяснение:\n\n".
- Если message_id отсутствует — лог WARNING, не отправляет (фолбэк не нужен для MVP).

## 6. Интеграция с day7

Точка создания explanation row: ПОСЛЕ подтверждённой отправки base alert в Telegram.

Конкретно: в месте, где alert_deliveries обновляется на status='sent' и сохраняется message_id, ДОБАВЛЯЕТСЯ вызов create_pending_explanation. Условие вызова: settings.ai_explanations_enabled и наличие settings.anthropic_api_key.

create_pending_explanation:
- INSERT alert_explanations (pattern_trigger_id, alert_delivery_id, status='pending', cache_key=<вычислен сразу>, prompt_hash=<вычислен сразу>, prompt_context_json=<bounded>).
- ON CONFLICT (pattern_trigger_id) DO NOTHING — гарантия идемпотентности.

Гарантия порядка: base alert всегда отправлен раньше, чем explanation row создан. Worker может прислать второе сообщение только через ≥ AI_EXPLANATION_WORKER_POLL_SECONDS + latency Anthropic, что заведомо позже base alert.

При AI_EXPLANATIONS_ENABLED=false — блок выше не выполняется, alert_explanations НЕ растёт.

## 7. Prompt

### 7.1 System message (фиксированный, Russian output)

Ты — технический аналитик, объясняющий пользователю, почему сработал автоматический сигнал на крипторынке.

Правила:
1. Отвечай на русском языке.
2. НЕ давай торговых инструкций. Запрещены фразы вида "покупай", "продавай", "входи в позицию", "шорти", "лонгуй", "сейчас хороший момент для входа".
3. Структура ответа строго в четырёх блоках:
   - Почему сработал сигнал
   - Что усиливает сигнал
   - Что ослабляет сигнал
   - На какие метрики и условия смотреть дальше
4. Кратко, по делу, без hype, без эмодзи, без markdown-заголовков. Используй обычные строки и абзацы.
5. Не выдумывай данные, которых нет во входном контексте.
6. Если данных недостаточно для одного из четырёх блоков — напиши "недостаточно данных" в этом блоке.

### 7.2 User message (шаблон)

Plain text с секциями. Пример структуры:

    Актив: BTC
    Паттерн: RSI_oversold_4h
    Severity: medium
    Gate decision: allowed
    Сработавшие условия:
    - RSI(14) на 4h = 27.3 (порог < 30)
    - Объём за последний час выше среднего за 24ч на 41%

    Текущие индикаторы:
    - RSI(14) 4h: 27.3
    - Stoch K: 18.4
    - Premium/Discount: -1.2%

    Снапшот цены (последние 6 точек, 1h интервал):
    - T-5h: 67_120
    - T-4h: 66_850
    - T-3h: 66_400
    - T-2h: 65_900
    - T-1h: 65_700
    - T-0h: 65_550

### 7.3 cache_key

cache_key = sha256(f"{asset}|{pattern_name}|{severity}|{gate_decision}|{normalized_reason}").hexdigest()[:64]

normalized_reason: matched_conditions, отсортированные по имени условия, без числовых значений (только сам факт условия).

## 8. Cost cap

Алгоритм в начале process_task (после cache lookup):

    hour_count = SELECT COUNT(*) FROM alert_explanations
                 WHERE status IN ('running','completed','failed','failed_stale')
                 AND created_at > now() - interval '1 hour'
    if hour_count >= AI_EXPLANATION_MAX_PER_HOUR:
        return EXCEEDED_HOUR

    day_count = SELECT COUNT(*) FROM alert_explanations
                WHERE status IN ('running','completed','failed','failed_stale')
                AND created_at > now() - interval '1 day'
    if day_count >= AI_EXPLANATION_MAX_PER_DAY:
        return EXCEEDED_DAY

При EXCEEDED_*: status=skipped_cost_cap, error_message="hour cap reached" или "day cap reached", completed_at=now(). Telegram explanation НЕ отправляется.

## 9. Безопасность

- ANTHROPIC_API_KEY: только из env через Settings. Никогда не пишется в логи (даже DEBUG), маскируется в repr(). Не появляется в error_message.
- raw_payload алерта в Anthropic НЕ отправляется. Только нормализованные поля из §7.2.
- .env не читается из ai-модулей напрямую. Только через Settings.
- Codex deny-rules в .codex/requirements.toml остаются: sudo, .env, ssh, push, alembic upgrade, alembic downgrade, psql.
- AI-ответ НЕ интерпретируется как команда. Текст только пересылается в Telegram как есть, без парсинга и без выполнения.
- prompt_context_json не должен содержать ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL или другие credential-поля.

## 10. Тесты

Ориентир: +30 новых тестов, всего 282 + 30 = 312 зелёных.

Unit:
- prompt_builder: snapshot test структуры user message, truncation поведение, детерминированность cache_key.
- cost_limiter: граничные случаи (cap-1, cap, cap+1; пустая БД; только reused_cache в окне).
- cache lookup: попадание, промах, expired окно.
- anthropic_client: mock httpx, проверка retry, fallback model, маскировка ключа в repr.

Integration:
- explanation_service: completed path, failed path (Anthropic raises), timeout path, cache hit, cost cap exceeded, disabled config.
- worker: claim → process → release, конкурентный claim двух воркеров (SKIP LOCKED), reclaim stale.
- end-to-end: pattern_trigger → AlertGate allow → telegram delivery sent → explanation pending → explanation completed → telegram second message.

Тестовая БД: PostgreSQL для всех integration (как в day7). SKIP LOCKED доступен.

## 11. Acceptance criteria

- Все существующие 282 теста зелёные.
- Новых тестов ≥ 28, все зелёные.
- alembic upgrade head в dev применяется без ошибок, downgrade откатывает таблицу чисто.
- AI_EXPLANATIONS_ENABLED=false: поведение day7 идентично, alert_explanations таблица существует но пустая.
- AI_EXPLANATIONS_ENABLED=true без ключа: приложение стартует, WARNING в лог, alerts продолжают идти, alert_explanations НЕ растёт.
- AI_EXPLANATIONS_ENABLED=true с ключом: для каждого pattern_trigger после Telegram sent создаётся ровно одна alert_explanations row (unique constraint работает).
- Cost cap соблюдён: при достижении hour/day лимита новые explanations получают skipped_cost_cap, Anthropic не вызывается.
- ruff baseline не растёт сверх 238, новые файлы clean.
- mypy на новых модулях без ошибок.
- ANTHROPIC_API_KEY не появляется ни в одном тестовом артефакте и логе.

## 12. Известные ограничения и future work

- История похожих срабатываний в промпте — day 8.x или day 9.
- Edit Telegram message вместо second message — отдельная задача после стабилизации.
- Multi-channel delivery — после введения второго канала.
- Streaming responses — не нужны при коротких объяснениях.
- failed_after_api_call как отдельный статус — добавим если cost accounting начнёт расходиться с реальностью.
- Параллельная обработка > 1 task за тик — после observability метрик worker latency.

## 13. План работ для Codex CLI

Порядок коммитов:
1. Alembic миграция + модель SQLAlchemy AlertExplanation.
2. Settings расширение + .env.example.
3. anthropic_client (с mock-based unit тестами).
4. prompt_builder + cache_key.
5. cost_limiter + cache lookup.
6. explanation_service.
7. explanation_worker.
8. telegram sender extension.
9. Интеграция в day7 delivery hook + idempotency.
10. End-to-end integration tests.
11. README / DEPLOYMENT обновления — отдельным мини-PR в конце дня.

Каждый шаг — отдельный коммит, тесты зелёные на каждом шаге.
