Day 7: Telegram Integration
Status: draft for Operator review
Branch (planned): `day7/telegram-integration`
PR title (planned): `feat: Telegram integration MVP (#NN)`
Closes: Issue #NN (создать перед запуском Codex)
Goal
Поднять рабочий Telegram bot для Duzman, который:
отправляет AlertGate alerts в Telegram chat;
при первом старте присылает bounded startup digest;
принимает базовые команды управления (`/start /help /status /alerts /mute /unmute /snooze`);
хранит состояние доставки в отдельной таблице `alert_deliveries`.
End state: single-user Duzman получает AlertGate alerts в Telegram, может временно глушить уведомления и просматривать недавние alerts командой.
Context
AlertGate (Speka 4) уже эмитит alerts в БД с cooldown 2h, soft cap 3/hr, hard caps 10/hr и 30/day.
prod БД и dev БД делят один PostgreSQL `duzman` под ролью `duzman_app`.
alembic head на момент начала задачи: `c0d2f8e4a9b1`.
ANTHROPIC_API_KEY не нужен на этом этапе — это day 8.
Multi-chat и БД-таблица `telegram_subscribers` сознательно отложены до отдельной задачи.
Architecture decisions
D1. Конфигурация — через .env
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ALERT_POLL_INTERVAL_SECONDS=30
TELEGRAM_STARTUP_LOOKBACK_HOURS=24
TELEGRAM_ENABLED=true
```
Token и chat_id читаются только через settings layer (`os.getenv` / pydantic settings).
Token никогда не логируется и не печатается.
Если `TELEGRAM_BOT_TOKEN` или `TELEGRAM_CHAT_ID` не заданы — Telegram sending безопасно отключается с понятной ошибкой конфигурации в логах при старте, остальная система продолжает работать.
`.env.example` обновляется с новыми ключами (без значений).
D2. Обнаружение новых alerts — polling БД
Фоновая задача читает БД раз в `TELEGRAM_ALERT_POLL_INTERVAL_SECONDS` (default 30).
Запрос: AlertGate alerts без записи в `alert_deliveries` для channel=`telegram`, status в (`pending`, `failed` с retry budget).
AlertGate не вызывает telegram_sender напрямую. Развязка через БД.
Event bus/pub-sub не вводится — future optimization.
D3. Startup digest
При старте Telegram worker:
вычисляет окно `now - TELEGRAM_STARTUP_LOOKBACK_HOURS` (default 24).
выбирает AlertGate alerts в этом окне, у которых нет успешного `sent` delivery в Telegram.
отправляет их одним или несколькими сообщениями с явным префиксом "📋 Startup digest" (или эквивалентным маркером).
после старта отправляются только новые alerts.
Если `alert_deliveries` пустая (первый запуск) — все alerts из окна попадают в digest.
Защита от дублей: после отправки записывается delivery row, повторный рестарт не зашлёт то же самое.
D4. Delivery state — отдельная таблица `alert_deliveries`
Новая таблица:
```
alert_deliveries:
  id              BIGSERIAL PRIMARY KEY
  alert_id        BIGINT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE
  channel         VARCHAR(20) NOT NULL                  -- "telegram" для MVP
  status          VARCHAR(20) NOT NULL                  -- pending|sent|failed|acked|snoozed
  sent_at         TIMESTAMPTZ NULL
  ack_at          TIMESTAMPTZ NULL
  snooze_until    TIMESTAMPTZ NULL
  error_message   TEXT NULL
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()

Индексы:
  ix_alert_deliveries_alert_id_channel (alert_id, channel)
  ix_alert_deliveries_status_channel (status, channel)
  ix_alert_deliveries_sent_at (sent_at DESC)

UNIQUE constraint:
  uq_alert_deliveries_alert_channel (alert_id, channel) — один delivery row на (alert, channel)
```
Решения по схеме:
`ack_at` и `snooze_until` заложены сразу nullable — даже если ack-кнопки не реализуются в day 7, схема готова.
channel = "telegram" — single value для MVP, тип VARCHAR для будущих каналов.
Не хранить delivery state в самой таблице alerts — alert это аналитическое событие, delivery это состояние канала.
Alembic migration: добавить таблицу + индексы + FK + unique constraint. Down: drop table.
D5. Telegram API mode — long polling
Bot работает через `getUpdates` long polling.
Telegram worker запускается как managed async background task внутри существующего Duzman runtime/worker процесса.
НЕ запускать Telegram worker как side effect of import.
НЕ запускать Telegram worker внутри FastAPI request handler.
На day 7 не делать отдельный systemd-сервис для Telegram.
Если `TELEGRAM_BOT_TOKEN` или `TELEGRAM_CHAT_ID` не заданы — Telegram worker safely disabled с понятным log message при старте; остальная система продолжает работать.
Polling timeout и polling interval конфигурируемы через .env (можно дефолты в коде).
Webhook не реализуется — оставить как future enhancement, не добавлять заглушки или dead code.
D6. Commands set
Минимальный набор для day 7:
`/start` — приветствие, проверка живости, текущий статус: enabled/muted, poll interval, startup lookback, last alert timestamp.
`/help` — список команд и краткие описания.
`/status` — расширенный статус: Duzman alive, AlertGate enabled, Telegram delivery enabled/muted/snoozed, poll interval, lookback, last alert ts, last successful send ts.
`/alerts` — последние 5 AlertGate alerts (id, ts, asset, rule, message preview).
`/mute` — глобально отключает Telegram delivery для текущего `TELEGRAM_CHAT_ID`. Состояние хранится в БД (см. D7).
`/unmute` — включает обратно.
`/snooze 1h | 4h | 24h` — выставляет global `snooze_until` для Telegram delivery. Per-alert snooze не реализуется.
Команды от любого chat_id, кроме `TELEGRAM_CHAT_ID`, игнорируются с логом "ignored command from unauthorized chat".
D7. Mute/snooze persistence
Mute и snooze — глобальные для канала Telegram. Порядок выбора storage:
Если в проекте уже есть key-value runtime state layer — использовать его, ключи `telegram.muted`, `telegram.snooze_until`, `telegram.enabled`.
Если нет — создать singleton-таблицу `telegram_channel_state`:
```
telegram_channel_state:
  id              SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1)  -- singleton row
  enabled         BOOLEAN NOT NULL DEFAULT true
  muted           BOOLEAN NOT NULL DEFAULT false
  snooze_until    TIMESTAMPTZ NULL
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```
Семантические границы:
`telegram_channel_state` хранит только состояние канала: enabled / muted / snooze_until / updated_at.
`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` остаются только в `.env` / settings layer, никогда не пишутся в БД.
`alert_deliveries` остаётся отдельной таблицей для per-alert delivery status (sent/failed/acked/snoozed).
При отправке alert worker проверяет: `enabled=true AND muted=false AND (snooze_until IS NULL OR snooze_until <= now())`. Если условие не выполняется — delivery row создаётся со status=`snoozed`, alert не отправляется в Telegram, но фиксируется в БД (чтобы при unmute не было double-send).
D8. Inline buttons (Acknowledge, Snooze)
В day 7: только команды, inline-кнопки откладываются.
Причина: per-alert ack/snooze требует callback_query handler, маппинг alert_id ↔ message_id, политика идемпотентности. Это отдельный объём, не входящий в текущий минимум. Поля `ack_at` и `snooze_until` в `alert_deliveries` уже заложены под будущее расширение.
D9. Rate limits и safety
Telegram Bot API лимит: 30 messages/sec на бота, 1 message/sec на chat. Используем библиотеку с встроенным rate limiter (aiogram / python-telegram-bot) либо явно ограничиваем sending до 1 msg/sec.
AlertGate уже имеет hard caps 10/hr и 30/day — Telegram pipeline не вводит свой alert cap, только delivery rate limit.
При ошибке отправки: записать `status=failed`, `error_message`, retry с экспоненциальным backoff (3 попытки, потом оставить failed для ручной диагностики).
D10. Library choice
Зафиксировано: `python-telegram-bot` как preferred library для MVP.
Исключение: если repo уже имеет dependency на `aiogram` или явную convention — использовать существующий выбор (preflight `git grep` должен это проверить).
Long polling через `getUpdates`.
Webhook не реализуется на day 7.
Pin версии в `pyproject.toml`.
Specification zone (whitelist)
Allowed to create/modify:
```
src/duzman/telegram/                              # новый пакет
  __init__.py
  bot.py                                          # main bot worker
  sender.py                                       # отправка alerts
  poller.py                                       # БД polling task
  commands.py                                     # handlers команд
  formatters.py                                   # форматирование alert → текст
  state.py                                        # mute/snooze persistence
  config.py                                       # settings из .env
src/duzman/db/models.py                           # AlertDelivery, TelegramChannelState
src/duzman/db/repositories/alert_deliveries.py    # новый repo
src/duzman/db/repositories/telegram_state.py     # новый repo
src/duzman/db/alembic/versions/<new>_add_alert_deliveries_and_telegram_state.py
src/duzman/runtime/main.py / entrypoint           # подключение Telegram worker (если есть)
src/duzman/runtime/__init__.py                    # экспорт worker, если нужно
.env.example
pyproject.toml                                    # добавить telegram library
docs/TZ.md                                        # только секция Telegram integration
docs/ARCHITECTURE.md                              # добавить Telegram pipeline diagram/описание
tests/telegram/                                   # новые тесты
  test_sender.py
  test_poller.py
  test_commands.py
  test_formatters.py
  test_state.py
  test_startup_digest.py
tests/test_alert_deliveries_repository.py
tests/test_migration_metadata_consistency.py      # обновление списка миграций
```
Read-only:
`.env` (никогда не читать содержимое, только через settings)
любые секреты, токены, ssh
`/opt/duzman` (prod)
prod БД
`config/patterns.yaml`
unrelated collectors/services
GitHub workflow/template файлы
docs unrelated to Telegram
Если нужен файл вне whitelist — остановиться и эскалировать.
Hard prohibitions
НЕ читать и не печатать `.env`.
НЕ коммитить значения `TELEGRAM_BOT_TOKEN` или `TELEGRAM_CHAT_ID`.
НЕ запускать `alembic upgrade head` на prod БД.
НЕ выполнять live Telegram API calls в тестах.
НЕ менять AlertGate logic, thresholds, cooldown, caps.
НЕ менять PriceSnapshot и связанные модели.
НЕ менять scheduler, collectors, repositories вне whitelist.
НЕ добавлять webhook handler.
НЕ добавлять multi-chat, telegram_subscribers, per-alert ack — это будущие задачи.
НЕ запускать sudo, apt, systemctl, Docker.
НЕ менять git remote, не пушить в main, не auto-merge.
Preflight (обязательный)
Перед началом имплементации Codex выполняет и репортит:
```
git status
git branch --show-current
git log --oneline --decorate -8
git rev-parse HEAD
git ls-files | grep -E 'telegram|alert|AlertGate|delivery'
.venv/bin/alembic heads
.venv/bin/alembic current
```
Working tree должен быть clean. Если нет — стоп.
Также: `git grep -n` по словам `telegram`, `Telegram`, `TELEGRAM_` чтобы убедиться, что нет существующих следов Telegram-интеграции, которые могут конфликтовать.
Implementation steps
Создать ветку `day7/telegram-integration` от свежего main.
Alembic migration: `alert_deliveries`, `telegram_channel_state`, индексы, FK, unique.
ORM модели `AlertDelivery`, `TelegramChannelState`.
Репозитории для обеих таблиц.
Settings layer (`src/duzman/telegram/config.py`) с pydantic settings и валидацией.
Formatter: AlertGate alert → Telegram message text (markdown safe, escape, не больше 4096 символов).
Sender: отправка одного alert, обработка ошибок, запись delivery row.
Poller: фоновая задача чтения новых alerts, вызов sender.
Startup digest: при старте читает окно lookback, формирует digest, шлёт с префиксом.
Bot worker: long polling, регистрация command handlers.
Commands: `/start /help /status /alerts /mute /unmute /snooze`.
Authorization: фильтр по `TELEGRAM_CHAT_ID`.
Mute/snooze check перед отправкой.
Интеграция в `runtime/main.py` (или эквивалент) — Telegram worker как опциональная задача, отключается если `TELEGRAM_ENABLED=false` или нет токена.
Тесты: unit (formatter, state), integration (poller + sender с mocked Telegram client, startup digest, commands).
Обновить `.env.example` и `pyproject.toml`.
Обновить `docs/TZ.md` (секция Telegram) и `docs/ARCHITECTURE.md`.
Обновить `tests/test_migration_metadata_consistency.py`.
Verification
```
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/
.venv/bin/alembic heads
.venv/bin/alembic upgrade head    # только dev БД, через source .env
.venv/bin/alembic downgrade -1
.venv/bin/alembic upgrade head
```
Все три миграционных шага должны быть зелёные. prod БД не трогаем.
Если в проекте есть offline runtime verification (`verify_read_only_api` или эквивалент) — запустить.
Definition of Done
Одна ветка `day7/telegram-integration`, один или минимум фокусных коммитов.
Все файлы внутри whitelist.
`.env` и секреты не тронуты.
prod БД не тронута.
Новая Alembic миграция с `alert_deliveries` и `telegram_channel_state`, обратимая.
ORM модели + репозитории.
Telegram bot worker запускается в режиме long polling.
Startup digest работает с bounded lookback.
Все 7 команд (`/start /help /status /alerts /mute /unmute /snooze`) реализованы.
Mute и snooze персистентны.
Sender обрабатывает ошибки и пишет в `alert_deliveries`.
AlertGate, scheduler, collectors не тронуты.
`pytest -q` зелёный (target: 268 + новые tests).
`ruff` baseline не ухудшен.
`mypy` baseline не ухудшен.
`alembic upgrade/downgrade` обратимы на dev БД.
`docs/TZ.md` и `docs/ARCHITECTURE.md` обновлены только в Telegram-секциях.
В PR description: ссылка на эту спеку, явный список того что НЕ сделано (multi-chat, inline buttons, webhook, ack per alert).
Final report (от Codex)
Initial HEAD commit.
Branch name.
Files changed.
New Alembic revision id.
Tables created + columns.
Commands implemented (список).
Library choice + version.
Test results.
Alembic head / downgrade / upgrade results.
Ruff/mypy results.
Grep cleanup results.
git status.
Commit hash(es).
Любые открытые риски или вопросы для Operator.
Out of scope (явно)
Multi-chat support (`telegram_subscribers` table).
Inline buttons (Acknowledge, Snooze per alert).
Webhook mode.
Per-alert snooze.
AI explanations (это day 8).
Изменения AlertGate.
Изменения thresholds/cooldown/caps.
Production deployment / systemd unit.
