# Duzman — Техническое задание v1.7

Персональный crypto metrics monitor. Этап А.

Версия 1.7 · 19 мая 2026

Version: v1.7
Fixed: 2026-05-19

---

## Изменения в версии 1.7

Версия 1.7 формализует GitHub-based multi-agent workflow.
Изменения процессные, не затрагивают контракт данных,
архитектуру продукта или hard caps.

Содержательные изменения:

- Раздел 0.4: переписан как полноценный change-control процесс
  (источник правды, версионирование PATCH/MINOR/MAJOR, процедура
  через PR, синхронные апдейты AGENTS.md/SKILL.md, откат)
- Раздел 0.5 (новый): GitHub как транспорт между агентами.
  Issue — контейнер одобренной задачи, PR — контейнер результата
  и ревью
- Приложение Г: формат спеки расширен с 7 до 8 полей.
  Добавлено поле "Зона спецификации" — whitelist файлов и
  директорий, доступных исполнителю для записи
- Приложение Е: обновлено под Issue/PR workflow. Push исполнителя
  в feature branch разрешён при одобренном Issue; push в main
  и protected branches запрещён; merge через PR
- Приложение Ж (новое): роли агентов и forbidden actions.
  Шесть ролей (Operator, Claude web, ChatGPT web, Claude Code,
  Codex CLI, Reviewer agent), общие forbidden actions, эскалация,
  разрешение конфликтов
- AGENTS.md и .claude/skills/duzman-conventions/SKILL.md
  синхронно обновлены под новый workflow
- docs/AGENT_PROTOCOL.md переписан под Issue → branch → PR →
  review → merge

Что НЕ изменилось: стек технологий, схема БД, метрики, шаблоны,
hard caps из раздела 0.2, граница этапа А/Б, AlertGate логика,
дефолт cooldown_hours.

---

## Изменения в версии 1.6

Версия 1.6 выпускается перед началом реализации Спеки 4 дня 6 (AlertGate). Содержит одно техническое уточнение по месту реализации дефолта cooldown.

Содержательные изменения:

- Раздел 4.6: явно зафиксировано, что дефолт `cooldown_hours = 2 часа` для шаблонов, у которых поле явно не задано в `patterns.yaml`, реализуется в Pydantic-модели `PatternDefinition` (`src/duzman/patterns/models.py`) на этапе загрузки конфигурации (Спека 1 дня 6). AlertGate всегда получает заполненное значение и НЕ содержит собственного fallback по cooldown

Что НЕ изменилось: стек технологий, схема БД (изменений в DDL нет), перечень метрик, hard caps из раздела 0.2, перечень шаблонов из Приложения А, граница этапа А/Б, workflow с агентами (Приложение Е), порядок проверок AlertGate, источник правды для счётчиков на дне 6 (`pattern_triggers.conditions_snapshot.gate_decision`).

---

## Изменения в версии 1.5

Версия 1.5 выпускается перед Спекой 4 дня 6 (AlertGate). Содержит формализацию
порядка проверок в AlertGate и определение источника правды для счётчиков на
дне 6.

Содержательные изменения:

- Раздел 4.6: добавлен явный порядок проверок AlertGate
(cooldown -> daily hard cap -> hourly hard cap -> soft cap) и явное
определение того, что в счётчики soft cap (3/час) и hourly hard cap (10/час)
входят только решения ALLOW. Suppress-решения фиксируются в pattern_triggers,
но не накручивают счётчики
- Раздел 7.7: добавлено, что на дне 6 AlertGate сохраняет своё решение
(GateDecision) в pattern_triggers.conditions_snapshot.gate_decision как
временный источник правды для счётчиков. На дне 7 после реализации Telegram
источником станет alerts_sent
- Приложение Б: добавлен комментарий к pattern_triggers.conditions_snapshot
про поле gate_decision на дне 6

Что НЕ изменилось: стек технологий, схема БД (изменений в DDL нет), перечень
метрик, hard caps из раздела 0.2, перечень шаблонов из Приложения А, граница
этапа А/Б, workflow с агентами (Приложение Е).

---

## Изменения в версии 1.4

Версия 1.4 выпускается перед началом дня 6 (Pattern Engine). Содержит
уточнения, выявленные при детализации структуры pattern engine и при
подготовке dev-окружения для миграций.

Содержательные изменения:

- Раздел 0.3: явно зафиксировано, что Linux-пользователь duzman и
PostgreSQL-роль duzman_app — это разные сущности. Зафиксировано, что
на этапе А база данных PostgreSQL общая для dev (~/duzman) и prod
(/opt/duzman). Разделение проходит по уровню .env и Linux-юзеру,
не по БД
- Раздел 4.3: число стартовых шаблонов изменено с 8 до 10. Шаблоны А.3
Capitulation candidate и А.4 Distribution top candidate расщеплены на
два варианта каждый по asset-классу (_majors для BTC/ETH с порогом
ликвидаций $100M; _alts для SOL/SUI/TON/UNI с порогом $20M). Это
техническое уточнение реализации, семантика шаблонов из v1.3 сохранена
- Раздел 4.6: переписан полностью. Антиспам и cooldown теперь описаны
через явную трёхуровневую иерархию ограничений: soft cap 3 алерта в час,
hard cap 10 алертов в час, hard cap 30 алертов в сутки. Для каждого уровня
явно описано поведение CRITICAL-алертов
- Раздел 7.7 (День 6): добавлено уточнение — записи в таблицу
pattern_triggers создаются для каждого сработавшего шаблона
независимо от решения AlertGate. Поле alert_sent остаётся FALSE на
дне 6 и обновляется на TRUE на дне 7 после успешной отправки в Telegram
- Раздел 8.1: число шаблонов в технических критериях изменено с 8 на 10
- Раздел 9.1: число стартовых шаблонов в границе этапа А изменено с 8 на 10
- Приложение А: А.3 и А.4 переписаны как два шаблона каждый
(_majors и _alts) с явными per-asset-class порогами и явными
применимыми активами

Что НЕ изменилось: стек технологий, схема БД, перечень метрик, hard
caps из раздела 0.2, граница этапа А/Б, workflow с агентами (Приложение Е).

---

## Изменения в версии 1.3

Версия 1.3 фиксирует фактический ход реализации после дней 1-3 и формализует процесс работы нескольких AI-агентов (Claude, Claude Code, Codex CLI, ChatGPT).

Содержательные изменения:

- Раздел 0.3: разделение dev/prod директорий — разработка в `~/duzman` под пользователем `ubuntu`, production deployment в `/opt/duzman` под пользователем `duzman`
- Раздел 0.4 (новый): процесс изменения ТЗ — ни один агент не отступает от ТЗ без явного апдейта документа
- Раздел 4.9: добавлены read-only ingestion endpoints, реализованные на дне 3 (`/api/market-data/prices/latest`, `/source-health`, `/ingestion-status`, `/ingestion-alerts`)
- Раздел 5.10: добавлен `docs/ARCHITECTURE.md` — обновляется в конце каждой задачи
- Раздел 6.3: добавлен модуль `src/duzman/runtime/` (entrypoints для one-shot команд и offline verification)
- Раздел 7.3 (День 2): зафиксированы фактические артефакты — src-layout, editable install, pytest с моками httpx, `verify_local_database`
- Раздел 7.4 (День 3): переструктурирован. День 3 = публичные коллекторы Binance/CoinGecko + ingestion health observability + read-only API foundation
- Раздел 7.5 (День 4): новое содержание — Bybit + OKX коллекторы, индикаторы RSI/Stochastic/Volatility, Premium/Discount
- Дни 5-11: пронумерованы со сдвигом на 1
- Раздел 7.10 (День 9, ранее 8): добавлен deployment-шаг — копирование актуального кода из `~/duzman` в `/opt/duzman`
- Приложение Е (новое): процесс работы нескольких AI-агентов

Что НЕ изменилось: стек технологий, схема БД, перечень метрик, перечень шаблонов, hard caps, граница этапа А/Б.

---

## 0. Рамки решения

### 0.1. Допущения

Решение опирается на следующие допущения. Если какое-то перестанет быть верным — задача пересматривается.

- Binance public API остаётся доступным без авторизации для endpoints цен, OHLCV, funding, OI, long/short
- Bybit и OKX public API остаются доступными без авторизации
- CoinGlass free API доступен с лимитом достаточным для одного запроса в час по каждому endpoint
- Farside Investors публикует данные ETF flows в открытом HTML формате
- Telegram Bot API бесплатен для нашего объёма
- OVHcloud VPS-2 SLA достаточен для целевых 99% доступности
- Anthropic Claude API остаётся доступным с pay-as-you-go биллингом
- Operator имеет техническую дисциплину для работы с менеджером паролей и SSH-ключами

### 0.2. Hard caps

Эти лимиты — защита от багов. При превышении система выполняет соответствующее защитное действие, не пытается «исправиться» автоматически.

| Что лимитируется | Значение | Действие при превышении |
| --- | --- | --- |
| Алерты в Telegram в час | 10 | Дальнейшие алерты до конца часа в очередь, в Telegram сводный «N suppressed» |
| Алерты в Telegram в сутки | 30 | Pattern engine остановлен до 00:00 UTC, алерт в системный канал |
| Расход Anthropic API в месяц | $5 | AI-объяснения отключаются до конца месяца |
| Запросы к одному внешнему API в минуту | 30 | Запросы троттлятся локально |
| Запросы к Duzman REST API в минуту | 60 на IP | 429 Too Many Requests |
| Размер БД Duzman | 10 GB | Системный алерт + уменьшение ретенции на 30 дней |
| Memory сервиса | 2 GB | Системный алерт, при 3 GB — рестарт через systemd |
| CPU процесса в среднем | 30% за 5 минут | Системный алерт |
| Размер backup-файла в Telegram | 50 MB | Bypass Telegram, только OneDrive с уведомлением |

Каждый hard cap реализуется в коде явной проверкой и явным действием.

### 0.3. Что выходит за рамки и не реализуется

Помимо общего списка не-целей в секции 1.3, явно НЕ реализуется в этом проекте никогда:

- Любое автономное размещение торговых ордеров
- Хранение приватных ключей кошельков, seed-фраз, любых credentials с trade-permissions
- Передача данных Operator-а третьим сторонам, кроме явно используемых внешних API
- Multi-user режим, разделение прав, audit log с точки зрения compliance
- Real-time исполнение по сигналу алерта
- Обработка персональных данных третьих лиц

Новое в v1.3 — разделение dev и prod директорий:

- Разработка ведётся в `~/duzman` под пользователем `ubuntu`. Здесь работают Codex CLI, Claude Code, и сам Operator. Здесь `git push/pull`
- Production deployment — в `/opt/duzman` под пользователем `duzman` без sudo. Systemd запускает `duzman.service` из `/opt/duzman`
- Процесс деплоя: на дне 9 настраивается скрипт копирования из `~/duzman` в `/opt/duzman` с последующим `systemctl restart`
- AI coding agents (Claude Code, Codex) НЕ имеют доступа к `/opt/duzman`. Они работают только в `~/duzman`

На этапе А база данных PostgreSQL — единая для dev и prod. Разделение между средами проходит по уровню .env (свой файл в ~/duzman/.env для dev, свой в /opt/duzman/.env для prod) и по Linux-пользователю, а не по отдельным БД

Linux-пользователь duzman и PostgreSQL-роль duzman_app — разные сущности. Linux-пользователь владеет файлами в /opt/duzman и под ним работает systemd-сервис. PostgreSQL-роль duzman_app — это credential для подключения к БД, используется и dev, и prod-окружениями

### 0.4. Процесс изменения ТЗ

Новое в v1.7: раздел переписан как полноценный change-control.
docs/TZ.md — единственный источник правды для всех агентов.

0.4.1. Источник правды

docs/TZ.md в ветке main — первичный канонический источник.
Любой gist-mirror, README-ссылка или внешняя копия — вторичны
и обновляются вручную после merge. При расхождении главенствует
main.

0.4.2. Кто инициирует изменение

Любой агент (Claude web, ChatGPT, Claude Code, Codex CLI,
reviewer-agent) может предложить изменение ТЗ, но не вносит его
самостоятельно. Operator также может инициировать изменение
сам. Решение о принятии изменения — всегда за Operator.

Если исполнитель в процессе работы обнаруживает, что ТЗ
требует доработки, он останавливается, описывает проблему и
предлагаемое изменение, и ждёт решения Operator. Никакой агент
не считает имплементированное отклонение принятым, пока
docs/TZ.md не обновлён явно.

0.4.3. Версионирование

PATCH (X.Y.Z, например 1.7.1): опечатки, уточнения формулировок,
исправления ссылок. Без изменения контрактов и без новых
разделов.

MINOR (X.Y, например 1.8): новые разделы или приложения, новые
поля в существующих структурах без ломки совместимости с уже
реализованным кодом и конвенциями. Процессные изменения.

MAJOR (X.0, например 2.0): ломающие изменения контракта данных,
схемы БД, hard caps из раздела 0.2, ролей агентов или ключевых
интерфейсов. Переход к этапу Б — отдельно по разделу 5.11 и
разделу 9.

0.4.4. Процедура

Изменение ТЗ вносится через Pull Request в docs/TZ.md.

Тело PR содержит:
- Тип изменения: PATCH / MINOR / MAJOR
- Затронутые разделы (список номеров и заголовков)
- Summary в 2-5 строк

Содержание PR:
- Обновлённый docs/TZ.md с новой версией в шапке и новой секцией
  "Изменения в версии X.Y" в начале документа (после шапки,
  перед предыдущей секцией изменений)
- Копия предыдущей версии скопирована в docs/archive/TZ_vX.Y.md
  в том же PR
- Обновлённая таблица "Контроль версий" в конце документа

0.4.5. Синхронные апдейты конвенций

Если изменение ТЗ затрагивает конвенции, роли или forbidden
actions, в том же PR обновляются:
- AGENTS.md
- .claude/skills/duzman-conventions/SKILL.md
- docs/AGENT_PROTOCOL.md, если он существует

Расхождение между docs/TZ.md и файлами конвенций — баг
документации, фиксируется ближайшим PR.

0.4.6. Синхронные апдейты производных документов

Если в репозитории присутствуют производные документы, отражающие срез
TZ на момент их создания и несущие в шапке или тексте явную привязку к
версии и дате фиксации TZ формата
`Техническое задание vX.Y от YYYY-MM-DD` или
`Based on: Техническое задание vX.Y от YYYY-MM-DD`,
то в PR на bump версии TZ они обновляются на новую версию и новую
дату фиксации.

К этой категории относятся:
- README.md
- ARCHITECTURE.md (когда появится)
- другие живые производные документы того же класса

К этой категории НЕ относятся (привязку к версии не несут, при bump
не обновляются):
- AGENTS.md, .claude/skills/duzman-conventions/SKILL.md,
  docs/AGENT_PROTOCOL.md, docs/REVIEW_PROTOCOL.md — это конвенции,
  они обновляются по правилам 0.4.5 при изменениях процессного характера,
  а не при каждом bump TZ
- .github/pull_request_template.md, CHANGELOG.md, самоссылки внутри
  docs/TZ.md — они говорят о TZ как о live-документе
- docs/archive/TZ_v*.md — иммутабельные снапшоты прошлых версий
- docs/specs/* — исторические документы, привязанные к версии TZ
  того момента, когда спека исполнялась; после мержа PR по спеке она
  не обновляется

0.4.7. Откат

Если после merge новая версия ТЗ выявила проблему, Operator
открывает PR на откат, восстанавливающий предыдущую версию из
docs/archive/TZ_vX.Y.md. Откат — это новый MINOR или MAJOR
бамп с явным указанием причины.

---

### 0.5. GitHub как транспорт между агентами

Новое в v1.7. Высокоуровневый инвариант, читается до приложений.
Детализация ролей и ограничений — Приложение Ж.

- GitHub Issue — контейнер одобренной задачи. Описание Issue
  содержит спеку в формате Приложения Г (8 полей) либо явную
  ссылку на спеку в репозитории
- Pull Request — контейнер результата и ревью. Один PR — одна
  задача из одного Issue
- Claude Code и Codex CLI работают автономно только от
  одобренного Issue/спеки и только внутри объявленной "Зоны
  спецификации" (поле 8 Приложения Г)
- Claude web и reviewer-agent ревьюят PR против: связанного
  Issue, docs/TZ.md, AGENTS.md/SKILL.md, diff, отчёта о
  верификации
- ChatGPT может черновиково писать и критиковать спеки по
  запросу Operator, но изменения в репозитории происходят
  только через обычный Git/PR workflow
- Operator — финальная инстанция по scope, merge, deploy и
  разрешению конфликтов. Operator не является штатным
  исполнителем agent workflow, но сохраняет право emergency
  и manual fixes
- Имплементированное отклонение от ТЗ не считается принятым,
  пока docs/TZ.md явно не обновлён (см. 0.4)

---

## Введение

Этот документ — техническое задание на этап А проекта Duzman, персонального инструмента мониторинга крипто-метрик. Документ описывает что строится, как оно работает, из каких компонентов состоит, и в какой последовательности реализуется.

Версия 1.7 формализует GitHub-based multi-agent workflow и change-control процесс. Включает все уточнения версий 1.3 — 1.6.

Целевая аудитория документа:

- Operator — владелец, заказчик и пользователь системы
- Claude (через web-чат) — архитектор, авторский надзор, code review, изменения ТЗ
- AI coding agents (Claude Code, Codex CLI, Gemini CLI или другие) — исполнители на VPS
- ChatGPT — второй планирующий слой у Operator
- Внешние аудиторы или консультанты

---

## 1. Цель и не-цели проекта

### 1.1. Рабочее название

Проект называется Duzman. Имя рабочее, выбрано Operator-ом.

### 1.2. Цель этапа А

Создать персональный инструмент мониторинга крипто-метрик для одного пользователя, который:

- Автоматически собирает рыночные метрики по настраиваемому списку активов раз в час
- Хранит исторические значения в локальной базе данных
- Визуализирует текущее состояние и историю через web-дашборд
- Присылает алерты в Telegram при срабатывании шаблона состояния рынка
- Работает автономно на VPS без участия пользователя
- Логирует свою работу и сообщает о сбоях

Главное измеримое условие успеха: минимум 10 информативных алертов за первые 14 дней. Информативный = Operator оценивает алерт как полезный для понимания рыночной ситуации (не дубликат, не шум, не ложноположительный).

ВАЖНО: Этап А — про доставку информации. Помогает ли информация торговать прибыльно — оценивается эмпирически после месяца использования.

### 1.3. Не-цели этапа А

- Не торгует. Не размещает ордера. Не имеет API ключей с trade permissions
- Не даёт торговые рекомендации в формате купи/продай
- Не использует AI для генерации сигналов. AI — только для объяснений уже сработавших детерминированных алертов
- Не обслуживает других пользователей. Single-user
- Не покрывает все возможные метрики. Только список из секции 3
- Не интерпретирует данные на уровне рекомендаций
- Не работает в real-time. Минимальная задержка около часа

### 1.4. Целевая аудитория системы

Один пользователь: Operator. Финский резидент, swing-трейдинг крипты, использует derivatives metrics и technical analysis. Интерфейсы алертов на русском, дашборд на английском.

### 1.5. Системный контекст

VPS OVHcloud, Ubuntu 24.04, 12 GB RAM, 6 vCPU, 100 GB SSD. Доступ через SSH с Windows 11 ноутбука. Web-дашборд публично через HTTPS с защитой API-ключом.

---

## 2. Персона и Use Cases

### 2.1. Профиль Operator-а

- Опыт криптотрейдинга больше года
- Торгует BTC, ETH, SOL и инфраструктурные альткоины (SUI, TON, UNI)
- Использует деривативы плюс спот
- Горизонт сделок: часы — несколько дней (swing-трейдинг)
- Работает один
- Локация: Финляндия (Europe/Helsinki)

### 2.2. Use Case 1 — Утренний обзор

Каждое утро около 9:00 Helsinki. Длительность 2-3 минуты. Открывает дашборд, видит сводку: цены и изменения, RSI на 4 таймфреймах, funding по 3 биржам, OI, long/short ratio, ETF flows, ликвидации, сработавшие шаблоны за 24 часа.

### 2.3. Use Case 2 — Реакция на алерт

Получает Telegram-уведомление, оценивает за 30 секунд интересно или нет, при необходимости открывает дашборд для деталей.

### 2.4. Use Case 3 — Pre-trade проверка

Открывает детальный вид по активу, смотрит графики RSI, funding, OI, ликвидаций, ETF flows за 7-30 дней.

### 2.5. Use Case 4 — Управление списком монет

Редактирует `config/assets.yaml`, перезапускает сервис. Применяется за 60 секунд.

ВАЖНО: Добавление монеты возможно только если для неё доступны источники. ETF flows не существуют для SUI.

### 2.6. Use Case 5 — Реакция на сбой

Источник недоступен 3+ часа — уведомление в системный канал Telegram. Operator решает: подождать или зайти по SSH разбираться.

### 2.7. Что не является use case-ом

- Multi-user сценарии
- Mobile-приложение
- Voice-команды
- Интеграция с биржевыми кошельками
- Парсинг новостей и социальных сетей

---

## 3. Функциональные требования: метрики

Стартовый список активов: BTC, ETH, SOL, SUI, TON, UNI. Конфигурируется через `config/assets.yaml`.

Точное время часового сбора: XX:17 каждого часа UTC. Binance funding refresh в 00:00, 08:00, 16:00 UTC — сбор в :17 захватывает уже свежий funding. Середина часа минимизирует совпадение с пиковыми моментами на биржах.

ETF flows собираются раз в день в 02:17 UTC (это 21:17 NY time, ETF flows уже опубликованы за прошлый день).

### 3.1. Цены и объёмы

- Применимо: все 6 активов
- Источник: Binance public API. Fallback: CoinGecko
- Частота: раз в час в XX:17
- Хранение: таблица `price_snapshots`

### 3.2. RSI

- Все 6 активов, таймфреймы 1h, 4h, 1d, 1w
- Источник: расчёт через pandas-ta из OHLCV Binance, период 14

### 3.3. Stochastic Oscillator

- Таймфреймы: 1h, 4h. Параметры: %K=14, %D=3, smoothing=3

### 3.4. Funding Rate

- Источники: Binance, Bybit, OKX. 18 значений каждый час

### 3.5. Open Interest

- Источники: 3 биржи + агрегированный через CoinGlass. 24 значения каждый час

### 3.6. Long/Short Ratio

- Источники: 3 биржи, типы `global_accounts` и `top_traders`. 36 значений каждый час

### 3.7. Liquidations

- Источник: CoinGlass free API

Упрощённая liquidation heatmap в этапе А:

- Два timeframes: 24h и 7d
- Только BTC и ETH
- Бакеты: 1% от текущей цены
- Источник: CoinGlass `liquidationHeatMap` endpoint (free tier)
- Fallback: если CoinGlass не отдаёт — в дашборде ссылка «View on CoinGlass»

### 3.8. ETF Flows (BTC, ETH)

- Источник: Farside Investors, парсинг HTML
- Частота: раз в день в 02:17 UTC

ВНИМАНИЕ: Farside может изменить структуру HTML. Парсер должен валидировать схему и логировать ошибки.

### 3.9. Volatility

Реализованная, 24h, annualized. Расчёт из исторической цены.

### 3.10. BTC Dominance

Источник: CoinGecko Global API.

### 3.11. Fear & Greed Index

Источник: Alternative.me API. Раз в день.

### 3.12. Premium/Discount Perpetual vs Spot

Вычисляется из существующих коллекторов. 18 значений каждый час.

### 3.13. Что НЕ включено в этап А

- CVD, Exchange netflow, Stablecoin supply, DVOL — этап Б
- Полноценная liquidation heatmap CoinGlass — этап Б
- Sentiment из соцсетей, Whale alerts — этап Б+

### 3.14. Сводная нагрузка

Около 182 числовых записей в БД на каждый часовой цикл. За год при ретенции 180 дней — порядка 800 тысяч записей, 200-400 MB. API requests: примерно 70 в час суммарно.

---

## 4. Алерты как шаблоны состояний

### 4.1. Парадигма

Алерт срабатывает только когда комбинация метрик складывается в распознаваемый паттерн. Метрика сама по себе порог пересечь может — алерта нет. Несколько метрик в совокупности образуют состояние — это алерт.

В дашборде по-прежнему видно всё. Telegram присылает только сложившиеся картины.

### 4.2. Структура шаблона

Каждый шаблон описан в `config/patterns.yaml`. Пример:

```
- name: "leveraged_long_buildup"
  display_name: "Лонги накапливаются на росте"
  severity: WARNING
  applies_to: [BTC, ETH, SOL]
  conditions:
    all:
      - metric: RSI_4h
        operator: ">"
        value: 65
      - metric: funding_rate_avg
        operator: ">"
        value: 0.03
      - metric: oi_change_24h_pct
        operator: ">"
        value: 8
      - metric: price_change_24h_pct
        operator: ">"
        value: 2
  cooldown_hours: 6
```

### 4.3. Стартовый набор шаблонов

Десять шаблонов. Восемь концептуальных шаблонов из Приложения А, два из них (Capitulation candidate и Distribution top candidate) на этапе А расщеплены на два варианта каждый по asset-классу, так как для них порог ликвидаций задаётся per-asset-class. Полное описание см. в Приложении А.

- Leveraged long buildup (WARNING)
- Leveraged short buildup (WARNING)
- Capitulation candidate — majors (CRITICAL, BTC/ETH)
- Capitulation candidate — alts (CRITICAL, SOL/SUI/TON/UNI)
- Distribution top candidate — majors (CRITICAL, BTC/ETH)
- Distribution top candidate — alts (CRITICAL, SOL/SUI/TON/UNI)
- Funding dislocation (WARNING)
- ETF accumulation strong (INFO)
- ETF distribution strong (WARNING)
- Altcoin underperformance (WARNING)

### 4.4. Формат сообщения в Telegram

Алерт на русском, фактологический, с цифрами и кратким AI-объяснением. Структура: эмодзи severity, название шаблона, актив, дата UTC, секция «Что произошло» со списком условий и значений, секция «Почему это интересно» с AI-объяснением, секция «Контекст» с историческими данными, ссылка «Открыть дашборд».

На MVP дня 7 Telegram-бот работает через long polling (`getUpdates`) и
отправляет plain-text сообщения без webhook. Если `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID` не заданы или `TELEGRAM_ENABLED=false`, delivery
безопасно отключается; токен и chat id не пишутся в БД. Состояние доставки
фиксируется в `alert_deliveries`, глобальные `mute` / `snooze` — в
`telegram_channel_state`.

### 4.5. AI-объяснения

Генерируется через Anthropic API (Claude Sonnet 4.6) для каждого срабатывания. Единственное место использования AI в этапе А.

Промпт явно запрещает: рекомендации действий, прогнозы цены, процентные вероятности, конкретные исторические даты.

Промпт явно разрешает: описание механики, описание структурных ситуаций без прогнозов, указание на что обратить внимание.

Post-processing фильтр проверяет запрещённые фразы и логирует нарушения.

ВНИМАНИЕ: AI используется ИСКЛЮЧИТЕЛЬНО для объяснения уже сработавших детерминированных алертов. Решение генерировать ли алерт НИКОГДА не делается AI.

Стоимость: примерно $0.003 за алерт. При 2-5 алертах в день — $0.20-0.50 в месяц. Hard cap: $5/мес.

AI explanations реализуются как optional async background worker, запускаемый
через `python -m duzman.runtime.run_ai_explanation_worker`. Worker не блокирует
AlertGate и Telegram base delivery, читает pending alert_explanations из БД и
обращается к Anthropic API только при AI_EXPLANATIONS_ENABLED=true. При
выключенной фиче или отсутствии ANTHROPIC_API_KEY worker завершает работу
безопасно. Deployment как systemd-сервис — отдельная будущая задача.

### 4.6. Антиспам и cooldown

Защита от шума реализована тремя слоями.

Cooldown:

- Cooldown по `dedup_key` = `pattern_name + asset` — настраивается per pattern в `config/patterns.yaml` через поле `cooldown_hours`
- Default cooldown: если поле `cooldown_hours` явно не задано в `patterns.yaml` — значение 2 часа подставляется Pydantic-моделью `PatternDefinition` (`src/duzman/patterns/models.py`) на этапе загрузки конфигурации (Спека 1 дня 6). Это единственное место реализации дефолта. AlertGate всегда получает заполненное значение и НЕ содержит собственного fallback по cooldown
- В пределах окна cooldown повторное срабатывание того же шаблона на том же активе фиксируется в БД (`pattern_triggers`), но в Telegram не отправляется

Soft cap — глобальный лимит интенсивности:

- Не более 3 алертов в час суммарно по всем шаблонам и активам
- WARNING и INFO алерты сверх лимита подавляются (не отправляются)
- CRITICAL алерты этот лимит обходят (но проверяются по hard cap ниже)
- Сброс счётчика — на границе часа UTC

Hard cap — защита от багов (см. раздел 0.2):

- Не более 10 алертов в час суммарно (включая CRITICAL). При превышении дальнейшие алерты до конца часа уходят в очередь; в Telegram отправляется одно сводное сообщение «N suppressed»
- Не более 30 алертов в сутки суммарно (включая CRITICAL). При превышении pattern engine останавливается до 00:00 UTC, в системный Telegram-канал отправляется алерт о срабатывании hard cap
- Сводное сообщение «N suppressed» само НЕ учитывается в счётчиках 3/час и 10/час

Порядок проверок в AlertGate (от строгого к мягкому):

1. Cooldown по `dedup_key` — если в окне cooldown уже был ALLOW по тому же шаблону на том же активе, текущий триггер подавляется (`SUPPRESS_COOLDOWN`)
2. Hard cap 30/сутки — если суточный счётчик ALLOW достиг 30, pattern engine остановлен до 00:00 UTC; все триггеры (включая CRITICAL) подавляются (`SUPPRESS_HARD_CAP_DAY`)
3. Hard cap 10/час — если часовой счётчик ALLOW достиг 10, триггер подавляется (включая CRITICAL) (`SUPPRESS_HARD_CAP_HOUR`)
4. Soft cap 3/час — если часовой счётчик ALLOW достиг 3 и severity не CRITICAL, триггер подавляется (`SUPPRESS_SOFT_CAP`)
5. Иначе — `ALLOW`

Если ни одна проверка не сработала — решение `ALLOW`. CRITICAL обходит только soft cap (шаг 4), но всё ещё подчиняется cooldown и обоим hard cap.

Что считается в счётчики:

- В часовой счётчик (3/час и 10/час) и в суточный счётчик (30/сутки) входят ИСКЛЮЧИТЕЛЬНО решения `ALLOW`
- Решения `SUPPRESS_COOLDOWN`, `SUPPRESS_SOFT_CAP`, `SUPPRESS_HARD_CAP_HOUR`, `SUPPRESS_HARD_CAP_DAY` записываются в `pattern_triggers`, но в счётчики не входят
- Сводное сообщение «N suppressed» в счётчики не входит
- Часовой счётчик сбрасывается на границе часа UTC; суточный — на границе суток UTC

Источник правды для счётчиков:

- На дне 6 (Telegram-отправка ещё не реализована) AlertGate сохраняет своё решение в поле `pattern_triggers.conditions_snapshot.gate_decision` (одно из `ALLOW` / `SUPPRESS_COOLDOWN` / `SUPPRESS_SOFT_CAP` / `SUPPRESS_HARD_CAP_HOUR` / `SUPPRESS_HARD_CAP_DAY`). Счётчики ALLOW рассчитываются как `COUNT(*) FROM pattern_triggers WHERE conditions_snapshot->>'gate_decision' = 'ALLOW' AND ts >= window_start`
- На дне 7 после реализации Telegram-отправки источником правды для доставки становится таблица `alert_deliveries`. Поле `gate_decision` в `conditions_snapshot` остаётся как audit trail для всех Suppress-решений

### 4.7. Daily Digest

Раз в сутки в 06:17 UTC одно сообщение со сводкой за 24 часа. Не входит в дневной лимит.

### 4.8. Ожидаемый объём

- Спокойный день: 0-2 алерта
- Активный день: 3-6 алертов
- Экстремальный день: 5-10 алертов
- В среднем: 1-3 алерта в день

### 4.9. REST API

Базовый префикс: `/api/v1/` для основных endpoints, `/api/market-data/` для read-only ingestion endpoints.

Основные endpoints (`/api/v1/`):

- `GET /api/v1/state` — concise снапшот
- `GET /api/v1/state/full` — снапшот + история 24h
- `GET /api/v1/assets/{symbol}` — полная картина по активу
- `GET /api/v1/metrics/{metric}` — историческая выборка
- `GET /api/v1/alerts?since={ts}` — список алертов
- `GET /api/v1/patterns/recent` — сработавшие шаблоны за 24h
- `GET /api/v1/health` — статус системы
- `GET /docs` — автоматическая OpenAPI документация

Read-only ingestion endpoints (`/api/market-data/`). Новое в v1.3. Реализованы на дне 3 для observability над процессом сбора данных. Читают уже персистентные данные, не запускают сбор.

- `GET /api/market-data/prices/latest` — последние цены из `price_snapshots`
- `GET /api/market-data/source-health` — статус источников
- `GET /api/market-data/ingestion-status` — общий статус сбора с полем `ingestion_health_summary`
- `GET /api/market-data/ingestion-alerts` — детерминированные алерты: missing data, stale data, unhealthy sources

Авторизация:

- API-ключ 64 hex-символа в заголовке `X-API-Key`
- Генерация: `openssl rand -hex 32`
- Хранение: `.env` с правами 600
- Открытые без auth: `/health`, `/api/market-data/ingestion-status`

Rate limiting: 60 запросов в минуту с одного IP. Не применяется к localhost.

### 4.10. Безопасность

Базовая разумная гигиена для публичного API.

Транспортный уровень:

- HTTPS обязателен через Let's Encrypt + Caddy
- HTTP редиректится на HTTPS

Сетевой уровень:

- UFW: открыты только 22 и 443
- Fail2ban на SSH: 5 неудачных попыток — час блокировки
- SSH только по ключу, password authentication отключена

Системный уровень:

- Production сервис работает под пользователем `duzman` без sudo, из `/opt/duzman`
- Разработка под пользователем `ubuntu`, из `~/duzman`
- Автообновления безопасности через unattended-upgrades

Управление секретами:

В системе хранится: Telegram bot token, Telegram chat IDs, API ключ Duzman REST API, Anthropic API ключ, пароль БД, OneDrive refresh token.

Все секреты в `/opt/duzman/.env` с правами 600, читаемые только пользователем `duzman`. В git не коммитятся.

ВНИМАНИЕ: Anthropic API ключ для Duzman должен храниться ИСКЛЮЧИТЕЛЬНО в `.env` файле Duzman. НЕ ДОЛЖЕН быть установлен как глобальная переменная `ANTHROPIC_API_KEY` в shell profile. Причина: AI coding agent при обнаружении глобальной переменной может использовать её для оплаты вместо подписки.

---

## 5. Нефункциональные требования

### 5.1. Доступность

Целевая 99% в месяц (около 7 часов простоя). Не входит: деградация одного источника, плановая перезагрузка.

### 5.2. Производительность

- Цикл сбора: до 5 минут (целевое 30-60 секунд)
- API `/state`: до 1 секунды
- Дашборд: первая загрузка до 3 секунд, обновление до 1 секунды

### 5.3. Надёжность сбора

- Retry: 30 секунд, 2 минуты, далее unavailable
- Источник недоступен 3+ часа — системный алерт
- Продолжение работы в degraded режиме

### 5.4. Восстановление после сбоев

- systemd auto-restart, до 60 секунд после reboot
- Максимум 5 рестартов за 10 минут — далее останов
- При недоступности БД — degraded mode с памятью
- При пропуске часов — восстановление из API при старте

### 5.5. Ретенция

- По умолчанию 180 дней, настраивается
- Исключения: `pattern_triggers`, `alerts_sent`, `user_feedback` — постоянно
- ETF flows — постоянно (микро-объём)

### 5.6. Бэкапы

Selective backup — только незаменимое:

- YAML-конфиги, `.env`
- Таблицы `pattern_triggers`, `alerts_sent`, `user_feedback`, `etf_flows`
- НЕ бэкапим raw metrics (восстановимы из API)

Стратегия:

- Ежедневно в 02:30 UTC — зашифрованный архив в приватный Telegram-канал
- Еженедельно (воскресенье 03:00 UTC) — копия на OneDrive через rclone
- Шифрование: gpg symmetric, пароль в Bitwarden
- Recovery: ручное, RTO 30 минут

Структура на OneDrive: папка `/Duzman/Backups/`, файлы `duzman-backup-YYYY-MM-DD.tar.gz.gpg`. 12 последних еженедельных. В Telegram — последние 30 ежедневных.

### 5.7. Мониторинг

- `/api/v1/health` endpoint
- `/api/market-data/ingestion-status` endpoint
- Отдельный Telegram-канал для системных алертов
- Логи в `/var/log/duzman/` с logrotate 30 дней

Системные алерты: источник недоступен 3+ часа, сервис рестартился, бэкап не выполнился, ошибка AI-объяснения, любой превышенный hard cap.

### 5.8. Лимиты ресурсов

- Python процесс: 200-500 MB RAM
- PostgreSQL: 500 MB - 1 GB RAM
- FastAPI: 100-200 MB RAM
- Caddy: 50 MB RAM
- Итого менее 20% ресурсов VPS

### 5.9. Обслуживаемость

Все параметры в YAML-файлах в `/opt/duzman/config/`. Изменение: edit + `systemctl restart`. Применение 60 секунд.

### 5.10. Документация

Новое в v1.3: добавлен `docs/ARCHITECTURE.md` как обязательный документ, обновляемый в конце каждой задачи.

- `README.md` — описание и quickstart
- `docs/ARCHITECTURE.md` — текущая архитектура. Обновляется любым агентом в конце каждой задачи
- `DEPLOYMENT.md` — развёртывание на новом VPS с нуля
- `TROUBLESHOOTING.md` — 10+ типичных проблем
- `CHANGELOG.md` — ведётся с дня 1
- `docs/TZ.md` — текущая версия ТЗ. Старые версии — в `docs/archive/`

### 5.11. Версионирование

- SemVer, начало 0.1.0
- 0.x — этап А (MVP)
- 1.0 — стабильная после 2 недель без критичных багов
- 2.x — этап Б

---

## 6. Архитектура и стек технологий

### 6.1. Высокоуровневая архитектура

Семь функциональных модулей в одном Python-процессе:

- Scheduler — часовой и ежедневный циклы
- Collectors — адаптеры к источникам
- Indicators Engine — RSI, Stochastic, Volatility
- Pattern Engine — проверка шаблонов
- Alert Dispatcher — cooldown, AI, форматирование, Telegram
- Web Service — FastAPI REST API и дашборд
- Runtime — one-shot entrypoints и offline verification (новое в v1.3)

Связь между модулями через БД PostgreSQL и in-process вызовы. Очереди не используются.

### 6.2. Стек технологий

| Технология | Выбор | Обоснование |
| --- | --- | --- |
| Язык | Python 3.12 | Финансовая экосистема, pandas-ta |
| Web framework | FastAPI | Async, OpenAPI, Pydantic |
| БД | PostgreSQL 16 | Надёжность, JSONB |
| ORM | SQLAlchemy 2.0 | Стандарт Python |
| Миграции | Alembic | Контролируемые изменения схемы |
| Scheduler | APScheduler | In-process, простой |
| HTTP | httpx | Async/sync, retries |
| Индикаторы | pandas-ta | Pure Python без системных deps |
| LLM | anthropic | Официальный SDK для Claude |
| Парсинг | beautifulsoup4 | Стандарт |
| Telegram | python-telegram-bot | Самый поддерживаемый |
| Reverse proxy | Caddy | Автоматический Let's Encrypt |
| Process manager | systemd | Стандарт Ubuntu |
| Frontend | Jinja2 + Plotly.js | Single-user, без SPA |
| Логи | structlog | JSON structured |
| Бэкапы | pg_dump + gpg + rclone | Стандарт unix |
| Тесты | pytest | Стандарт Python |

### 6.3. Структура проекта

Новое в v1.3: добавлен модуль `src/duzman/runtime/`. Структура отражает фактическое состояние после дня 3.

```
duzman/
├── README.md, docs/ARCHITECTURE.md, DEPLOYMENT.md, TROUBLESHOOTING.md, CHANGELOG.md
├── pyproject.toml, .env.example, .gitignore
├── docs/
│   ├── TZ.md (текущая версия ТЗ, источник правды для всех агентов)
│   ├── LOCAL_DEV_SETUP.md
│   ├── REPOSITORY_INVENTORY.md
│   └── archive/ (старые версии ТЗ)
├── config/
│   ├── assets.yaml, sources.yaml, patterns.yaml
│   ├── alerts.yaml, system.yaml
├── src/duzman/
│   ├── main.py, settings.py
│   ├── collectors/  (base, binance, bybit, okx, coinglass, farside, coingecko)
│   ├── indicators/  (rsi, stochastic, volatility)
│   ├── patterns/    (engine, conditions)
│   ├── alerts/      (dispatcher, telegram, formatter, ai_explainer)
│   ├── db/          (models, session, migrations/)
│   ├── api/         (routes, auth, schemas)
│   ├── dashboard/   (routes, templates/)
│   ├── scheduler/   (jobs)
│   └── runtime/     (one-shot entrypoints, verify_*, Day 8 smoke harness)
├── .claude/skills/duzman-conventions/SKILL.md
├── AGENTS.md (для Codex CLI)
├── .codex/ (Codex policy)
├── scripts/         (install.sh, deploy.sh, backup.sh, restore.sh)
├── deploy/          (duzman.service, Caddyfile, logrotate.conf)
└── tests/
```

### 6.4. Схема базы данных

Полная DDL см. Приложение Б.

### 6.5. Часовой цикл (XX:17 UTC)

- Scheduler запускает `collect_cycle`
- Collectors параллельно через `asyncio.gather`
- Raw данные → БД
- Indicators Engine считает производные
- Pattern Engine проверяет шаблоны
- Для совпавших: cooldown → `pattern_trigger` → AI-объяснение → формат → Telegram → `alerts_sent`

### 6.6. Daily обслуживание (02:30 UTC)

- Очистка данных старше 180 дней
- Бэкап → шифрование → Telegram
- По воскресеньям дублирование на OneDrive

### 6.7. Daily digest (06:17 UTC)

Сводка за 24 часа в основной Telegram-канал.

### 6.8. Что НЕ в архитектуре этапа А

- Микросервисы, Redis, message queue
- Docker / Kubernetes
- Multi-region, read replicas
- GraphQL, WebSocket к фронтенду

---

## 7. План реализации этапа А

11 рабочих дней по 6-8 часов или 4-5 календарных недель при работе по 2-3 часа в день. Каждый день заканчивается чем-то работающим.

Новое в v1.3: план удлинён с 10 до 11 дней из-за расширения дня 3 (ingestion observability). Дни 5-10 пронумерованы со сдвигом на 1.

### 7.1. Workflow разработки

- Operator — supervisor: контроль, решения, проверка
- Claude (web-чат) — архитектор: спецификации, code review, изменения ТЗ
- AI coding agents — исполнители: реализация по спецификациям, тесты

Подробнее: Приложения В и Е.

### 7.2. День 1 — Фундамент VPS

- Update Ubuntu + системные пакеты
- Python 3.12, PostgreSQL 16, Caddy, UFW, Fail2ban
- Linux-пользователь `duzman` без sudo, директория `/opt/duzman`
- systemd stub service
- Рабочая директория для разработки: `~/duzman` под `ubuntu`
- Клонирование репозитория в `~/duzman`
- rclone
- Установка AI coding agents (Claude Code, Codex CLI)

ВНИМАНИЕ: При установке coding agent НЕ устанавливать `ANTHROPIC_API_KEY` или `OPENAI_API_KEY` как глобальную переменную окружения.

### 7.3. День 2 — Цены и OHLCV, foundation

Уточнено в v1.3: зафиксированы фактические артефакты дня 2.

- `pyproject.toml` + зависимости, src-layout
- Editable install: `.venv/bin/python -m pip install -e .`
- Alembic первая миграция (initial schema)
- BinanceCollector + CoinGeckoCollector fallback (public endpoints)
- Price snapshot ingestion service + repository pattern
- Source health tracking (latency, ошибки)
- APScheduler с расписанием XX:17 (job зарегистрирован, не запущен автоматически)
- Structlog с safe event names, без raw payloads
- Pytest suite с моками httpx, оффлайн-тесты без живых API
- Runtime команды: `run_market_data_collection_once`, `verify_local_database`

### 7.4. День 3 — Ingestion observability и Read-only API

Уточнено в v1.3: день 3 переструктурирован. Bybit/OKX и индикаторы перенесены на день 4.

- FastAPI app factory `create_app()`
- Read-only endpoints: `/api/market-data/prices/latest`, `/source-health`, `/ingestion-status`, `/ingestion-alerts`
- Детерминированные ingestion health alerts (missing data, stale data, unhealthy sources)
- `ingestion_health_summary` в `/ingestion-status` (healthy/warning/critical)
- Runtime verification команда: `verify_read_only_api`
- Расширение Claude Code allow-rules в `.claude/settings.json`
- Подготовка `AGENTS.md` и `.claude/skills/duzman-conventions/SKILL.md`

### 7.5. День 4 — Bybit, OKX, индикаторы

Уточнено в v1.3: содержание перенесено с прежнего дня 3.

- BybitCollector (public funding, OI, long/short)
- OKXCollector (public funding, OI, long/short)
- RSI на 4 таймфреймах (1h, 4h, 1d, 1w) через pandas-ta
- Stochastic Oscillator (1h, 4h)
- Volatility realized 24h annualized
- Premium/Discount perpetual vs spot
- Запуск `duzman.service` через systemctl (replace stub ExecStart)

### 7.6. День 5 — Остальные метрики

- FarsideCollector (ETF flows BTC/ETH)
- CoinGlassCollector (ликвидации)
- BTC dominance + Fear&Greed
- Liquidation heatmap упрощённая (BTC, ETH, 24h+7d, бакеты 1%)

### 7.7. День 6 — Pattern Engine

- Загрузка `patterns.yaml`
- Pattern engine, evaluation
- Cooldown logic с дефолтом 2 часа (реализуется в Pydantic-модели `PatternDefinition` на этапе загрузки конфигурации; AlertGate работает с заполненным `cooldown_hours` и собственного fallback не имеет)
- AlertGate: cooldown -> daily hard cap -> hourly hard cap -> soft cap (порядок и определения см. раздел 4.6)
- Записи в `pattern_triggers` создаются для каждого сработавшего шаблона независимо от решения AlertGate; успешная Telegram-доставка фиксируется отдельной строкой `alert_deliveries`
- На дне 6 физическая отправка в Telegram НЕ реализуется. AlertGate возвращает `GateDecision` (одно из `ALLOW`, `SUPPRESS_COOLDOWN`, `SUPPRESS_SOFT_CAP`, `SUPPRESS_HARD_CAP_HOUR`, `SUPPRESS_HARD_CAP_DAY`) и сохраняет его в `pattern_triggers.conditions_snapshot.gate_decision`; на дне 7 delivery state переходит в `alert_deliveries`
- Тестирование 10 шаблонов на исторических данных (фикстуры с предзаписанными значениями метрик)

### 7.8. День 7 — Telegram и AI

- Telegram-бот через @BotFather, long polling (`getUpdates`), без webhook
- Telegram worker запускается явно как managed async background task и безопасно отключается при отсутствии `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- TelegramSender и formatter доставляют только AlertGate `ALLOW` alerts из `pattern_triggers`; AlertGate не вызывает Telegram напрямую
- Startup digest отправляет bounded список недоставленных alerts за `TELEGRAM_STARTUP_LOOKBACK_HOURS`
- `alert_deliveries` хранит per-alert delivery state (`sent`, `failed`, `acked`, `snoozed`); `telegram_channel_state` хранит global enabled/muted/snooze
- Команды MVP: `/start`, `/help`, `/status`, `/alerts`, `/mute`, `/unmute`, `/snooze`
- Inline buttons, multi-chat, webhook и per-alert snooze отложены
- AI-объяснитель Claude Sonnet 4.6 и Anthropic API — день 8, не часть Telegram MVP

### 7.9. День 8 — Дашборд и REST API

- FastAPI приложение полностью (включая `/api/v1/`)
- API auth middleware
- HTML + Jinja2 + Plotly.js
- Caddy конфиг

### 7.10. День 9 — Deployment и обслуживание

Новое в v1.3: явный deployment-шаг из `~/duzman` в `/opt/duzman`.

- Deploy script: копирование актуального кода из `~/duzman` в `/opt/duzman`, права для пользователя `duzman`
- Production `.env` в `/opt/duzman/.env` с правами 600
- Обновление `duzman.service`: `WorkingDirectory=/opt/duzman`, `User=duzman`, ExecStart на реальный entrypoint
- Daily backup (pg_dump + gpg + Telegram)
- Weekly OneDrive через rclone в `/Duzman/Backups/`
- Retention job
- Daily digest
- Системные алерты
- `/health` endpoint

### 7.11. День 10 — Тестирование

- 24 часа в полной конфигурации
- Ловля long-running багов
- Тест retry-логик (искусственный сбой источника)
- Тест восстановления после рестарта
- Recovery test (drop database → restore)

### 7.12. День 11 — Документация и релиз

- Доделка README, DEPLOYMENT, TROUBLESHOOTING
- Конфигурационный гайд
- Git tag 0.1.0
- Финальный бэкап
- Тест: Operator самостоятельно добавляет монету по гайду

---

## 8. Критерии готовности этапа А

### 8.1. Технические критерии

- Система работает под systemd под пользователем `duzman` из `/opt/duzman`, поднимается автоматически
- Все 13 категорий метрик собираются в XX:17 каждого часа
- История накоплена за минимум 7 дней
- Все 10 шаблонов проверяются каждый час
- Pattern triggers пишутся в БД с полным составом метрик
- AI-объяснения генерируются через Sonnet 4.6
- Post-processing фильтр работает
- Telegram-алерты доставляются
- Системные алерты в отдельный канал
- Daily digest в 06:17 UTC
- Web-дашборд через HTTPS
- REST API с правильным auth
- Бэкапы ежедневно в Telegram, weekly OneDrive
- Retention job удаляет данные старше 180 дней
- Health endpoint показывает корректный статус
- Recovery test пройден за 30 минут
- Все hard caps из раздела 0.2 реализованы и проверены

### 8.2. Качественные критерии

- Минимум 10 информативных алертов за первые 14 дней
- 80%+ алертов оценены Operator-ом как информативные
- Нет превышений hard caps из-за багов
- Нет ложноположительных срабатываний из-за багов
- AI-объяснения не содержат запрещённых фраз в 95%+ случаев

### 8.3. Документационные критерии

- `README.md` содержит описание и quickstart
- `docs/ARCHITECTURE.md` актуален на дату релиза
- `DEPLOYMENT.md` позволяет развернуть на новом VPS с нуля
- `TROUBLESHOOTING.md` покрывает 10+ типичных проблем
- `CHANGELOG.md` ведётся с дня 1
- `docs/TZ.md` в репозитории, доступен всем агентам

### 8.4. Operational критерии

- Системой можно пользоваться без разработчика 14+ дней
- Operator знает где смотреть логи, как проверить health

### 8.5. Финансовые критерии

- Расход Anthropic API менее $1 в месяц в стабильном режиме
- Hard cap $5/мес не срабатывает

### 8.6. Граница перехода к этапу Б

После выполнения всех критериев — этап А завершён. Решение о переходе к Б принимается отдельно, после минимум 30 дней эксплуатации.

Основной вопрос: помогает ли система Operator-у принимать более качественные торговые решения, по его субъективной оценке?

---

## 9. Граница этапа А и этапа Б

### 9.1. Что входит в этап А

| Категория | Конкретно |
| --- | --- |
| Метрики | Цены, RSI, Stochastic, Funding, OI, Long/Short, Liquidations (упрощ. heatmap), ETF flows BTC/ETH, Volatility, BTC.D, Fear&Greed, Premium/Discount |
| Активы | BTC, ETH, SOL, SUI, TON, UNI |
| Биржи | Binance, Bybit, OKX (только public API) |
| Источники aggregate | CoinGlass free, CoinGecko, Farside, Alternative.me |
| AI | Claude Sonnet 4.6 для текстовых объяснений к сработавшим шаблонам |
| Шаблоны | 10 стартовых из Приложения А |
| Доставка | Telegram (2 канала) |
| UI | Web-дашборд (HTTPS, single-user) |
| API | REST API с auth по ключу + read-only ingestion endpoints |
| Хостинг | Один OVH VPS, single-instance |
| Бэкапы | Daily Telegram + Weekly OneDrive |
| Мониторинг | `/health` + `/ingestion-status` + системный Telegram канал |

### 9.2. Что входит в этап Б (НЕ делается сейчас)

| Категория | Конкретно |
| --- | --- |
| Дополнительные метрики | CVD, Exchange netflow, Stablecoin supply, DVOL, полноценная CoinGlass heatmap |
| Sentiment | Twitter, Reddit, LunarCrush |
| On-chain | Whale alerts, Glassnode, CryptoQuant |
| AI расширения | AI-агенты для новостей, классификация narrative |
| AI-самообучение | Корректировка порогов на основе feedback |
| Post-trade analysis | Отметка факта сделки, post-trade отчёт |
| Backtesting | Прогон шаблонов на исторических данных |
| Дополнительные доставки | Email, Discord, SMS |
| MCP-обёртка | Опциональная |
| Платные источники | CoinGlass, Glassnode, CryptoQuant |

### 9.3. Что НЕ войдёт никогда

- Автономное размещение торговых ордеров
- Хранение приватных ключей с trade-permissions
- AI принимающий решения за Operator-а
- Multi-user режим, B2B продукт
- Реальные деньги под управлением системы

---

## Приложение А. Стартовый набор шаблонов

Десять шаблонов. Default cooldown 2 часа, если не указан явно (реализуется в Pydantic-модели `PatternDefinition` на этапе загрузки конфигурации).

Все шаблоны проверяются один раз в час после фазы сбора и расчёта индикаторов (job `patterns_evaluation` в XX:25 UTC по плану дня 6). Записи в `pattern_triggers` создаются для каждого сработавшего шаблона независимо от решения AlertGate.

### А.1. Leveraged long buildup (WARNING, BTC/ETH/SOL, cooldown 6h)

- RSI 4h > 65
- Funding средний по 3 биржам > +0.03%
- OI изменение 24h > +8%
- Цена изменение 24h > +2%

Описание: лонги пирамидингуют на ралли.

### А.2. Leveraged short buildup (WARNING, BTC/ETH/SOL, cooldown 6h)

- RSI 4h < 35
- Funding средний < -0.03%
- OI изменение 24h > +8%
- Цена изменение 24h < -2%

Описание: шорты накапливаются на падении.

### А.3-majors. Capitulation candidate — majors (CRITICAL, BTC/ETH, cooldown 4h)

- RSI 1d < 30
- Funding средний < -0.05%
- Ликвидации longs 24h > $100M
- Fear&Greed < 25

Описание: капитуляция на BTC/ETH с массовым закрытием лонгов.

### А.3-alts. Capitulation candidate — alts (CRITICAL, SOL/SUI/TON/UNI, cooldown 4h)

- RSI 1d < 30
- Funding средний < -0.05%
- Ликвидации longs 24h > $20M
- Fear&Greed < 25

Описание: капитуляция на альтах. Порог ликвидаций пропорционально меньше из-за меньшего размера рынка.

### А.4-majors. Distribution top candidate — majors (CRITICAL, BTC/ETH, cooldown 4h)

- RSI 1d > 70
- Funding средний > +0.05%
- Ликвидации shorts 24h > $100M
- Fear&Greed > 75

Описание: эйфория на BTC/ETH с массовым закрытием шортов.

### А.4-alts. Distribution top candidate — alts (CRITICAL, SOL/SUI/TON/UNI, cooldown 4h)

- RSI 1d > 70
- Funding средний > +0.05%
- Ликвидации shorts 24h > $20M
- Fear&Greed > 75

Описание: эйфория на альтах.

### А.5. Funding dislocation (WARNING, все 6 активов, cooldown 4h)

- Расхождение funding между биржами > 0.05%

Описание: рынок не сходится по funding между Binance/Bybit/OKX.

### А.6. ETF accumulation strong (INFO, BTC/ETH, cooldown 24h)

- 5 дней подряд положительный net flow
- Кумулятив за 5 дней > $1B (BTC) или $200M (ETH)

Описание: устойчивый приток в спотовые ETF.

### А.7. ETF distribution strong (WARNING, BTC/ETH, cooldown 24h)

- 5 дней подряд отрицательный net flow
- Кумулятив < -$500M (BTC) или -$100M (ETH)

Описание: устойчивый отток из спотовых ETF.

### А.8. Altcoin underperformance (WARNING, SOL/SUI/TON/UNI, cooldown 24h)

- BTC dominance изменение > +1% за 7 дней
- Цена альткоина против BTC < -5% за 7 дней

Описание: альт отстаёт от BTC на фоне роста доминирования BTC.

---

## Приложение Б. Схема базы данных

PostgreSQL 16. Time-series таблицы имеют индекс `(ts DESC, asset)`.

```
CREATE TABLE assets (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE price_snapshots (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    source VARCHAR(20) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    price_usd NUMERIC(20,8) NOT NULL,
    volume_24h_quote NUMERIC(20,2),
    price_change_24h_pct NUMERIC(8,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB
);
CREATE INDEX ix_price_snapshots_source_asset_ts ON price_snapshots(source, asset, ts);
CREATE INDEX ix_price_snapshots_ts ON price_snapshots(ts DESC);
CREATE INDEX ix_price_snapshots_source ON price_snapshots(source);

CREATE TABLE indicators (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    indicator_type VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10),
    value NUMERIC(12,4),
    parameters JSONB
);
CREATE INDEX idx_ind ON indicators(ts DESC, asset, indicator_type, timeframe);

CREATE TABLE funding_rates (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    exchange VARCHAR(20) NOT NULL,
    funding_rate_pct NUMERIC(10,6),
    next_funding_time TIMESTAMPTZ,
    predicted_rate NUMERIC(10,6)
);

CREATE TABLE open_interest (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    exchange VARCHAR(20) NOT NULL,
    oi_usd NUMERIC(20,2),
    oi_contracts NUMERIC(20,2)
);

CREATE TABLE long_short_ratio (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    exchange VARCHAR(20) NOT NULL,
    ratio_type VARCHAR(30) NOT NULL,
    long_pct NUMERIC(6,2),
    short_pct NUMERIC(6,2),
    ratio NUMERIC(10,4)
);

CREATE TABLE liquidations (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    longs_liquidated_1h_usd NUMERIC(20,2),
    shorts_liquidated_1h_usd NUMERIC(20,2),
    longs_liquidated_24h_usd NUMERIC(20,2),
    shorts_liquidated_24h_usd NUMERIC(20,2)
);

CREATE TABLE etf_flows (
    date DATE NOT NULL,
    asset VARCHAR(10) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    flow_usd_m NUMERIC(10,2),
    PRIMARY KEY (date, asset, provider)
);

CREATE TABLE global_metrics (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    metric_name VARCHAR(30) NOT NULL,
    value NUMERIC(12,4)
);

CREATE TABLE pattern_triggers (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    pattern_name VARCHAR(50) NOT NULL,
    asset VARCHAR(10) REFERENCES assets(symbol),
    severity VARCHAR(10) NOT NULL,
    conditions_snapshot JSONB,
    -- conditions_snapshot хранит снапшот значений метрик на момент срабатывания
    -- шаблона. На дне 6 (v1.5+) также содержит поле gate_decision: одно из ALLOW,
    -- SUPPRESS_COOLDOWN, SUPPRESS_SOFT_CAP, SUPPRESS_HARD_CAP_HOUR, SUPPRESS_HARD_CAP_DAY.
    -- Используется AlertGate как audit trail для решений ALLOW/SUPPRESS;
    -- delivery state Telegram хранится отдельно в alert_deliveries
    ai_explanation TEXT,
    alert_sent BOOLEAN DEFAULT FALSE,
    user_feedback VARCHAR(20),
    user_feedback_at TIMESTAMPTZ
);

CREATE TABLE alerts_sent (
    id BIGSERIAL PRIMARY KEY,
    pattern_trigger_id BIGINT REFERENCES pattern_triggers(id),
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    telegram_message_id BIGINT,
    delivery_status VARCHAR(20),
    delivery_error TEXT,
    dedup_key VARCHAR(100)
);
CREATE INDEX idx_alerts_dedup ON alerts_sent(dedup_key, sent_at DESC);

CREATE TABLE alert_deliveries (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES pattern_triggers(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    sent_at TIMESTAMPTZ,
    ack_at TIMESTAMPTZ,
    snooze_until TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_alert_deliveries_alert_channel UNIQUE (alert_id, channel)
);
CREATE INDEX ix_alert_deliveries_alert_id_channel
    ON alert_deliveries(alert_id, channel);
CREATE INDEX ix_alert_deliveries_status_channel
    ON alert_deliveries(status, channel);
CREATE INDEX ix_alert_deliveries_sent_at
    ON alert_deliveries(sent_at DESC);

CREATE TABLE telegram_channel_state (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    muted BOOLEAN NOT NULL DEFAULT FALSE,
    snooze_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE api_requests (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT NOW(),
    endpoint VARCHAR(100),
    ip_address INET,
    response_code INT,
    response_time_ms INT
);

CREATE TABLE source_health (
    source VARCHAR(20) PRIMARY KEY,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    consecutive_failures INT DEFAULT 0,
    status VARCHAR(20)
);
```

---

## Приложение В. Workflow разработки с coding agent

### В.1. Установка coding agent

Под пользователем `ubuntu` (не под `duzman`). Перед установкой проверить отсутствие переменных `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`.

### В.2. Безопасный запуск

- Работать под пользователем `ubuntu`, не под `duzman`
- Перед каждой большой задачей: `git commit`
- Узкие задачи, не «сделай всё что нужно»
- Читать diff перед commit
- Не давать задачи на работу с production `.env`

### В.3. Откат после ошибок

```
git status              # посмотреть изменения
git diff                # понять что именно
git reset --hard HEAD   # откатить всё
git checkout -- <file>  # откатить один файл
```

---

## Приложение Г. Spec format для агента-исполнителя

Каждая задача для agent-а — короткий документ из 8 полей:

- Название (одна строка, в snake_case или kebab-case)
- Контекст (1-2 предложения о модуле и роли)
- Цель (что должно работать в конце)
- Входы (данные, конфиги, окружение)
- Выходы (файлы, функции, записи в БД)
- Требования (библиотеки, паттерны, стиль, тесты)
- Критерии готовности (наблюдаемые)
- Зона спецификации (whitelist файлов и директорий)

Правила формулировки:

- Одна спецификация — одна узкая задача
- Конкретные имена файлов, классов, методов, таблиц
- Конкретные библиотеки, если важно
- Критерии готовности — наблюдаемые, не субъективные
- Hard caps и security ограничения — явно повторить

Зона спецификации:

- Явный whitelist файлов и директорий, которые исполнитель имеет
  право создавать или модифицировать в рамках данной задачи
- Всё остальное — read-only
- Если в процессе выясняется, что нужно тронуть файл вне зоны —
  исполнитель останавливается и эскалирует спеку на доработку
  по 0.4. Самовольное расширение зоны запрещено
- PR с diff за пределами объявленной зоны без явного одобрения
  Operator-ом отклоняется reviewer-agent с вердиктом
  REJECT_SCOPE_VIOLATION (см. Приложение Ж)

Что НЕ должно быть в спецификации:

- Архитектурные обоснования (это в ТЗ)
- Long-term планы
- Альтернативные подходы
- Эмоциональные оценки

---

## Приложение Д. Глоссарий

Краткий справочник крипто и технических терминов:

- Spot, Perpetual, Funding rate, OI, Long/Short ratio, Liquidation
- RSI, Stochastic, OHLCV, Volatility, Premium/Discount
- ETF flow, Farside, BTC dominance, Fear&Greed
- Squeeze, Capitulation, Distribution top
- API, REST, MCP, VPS, HTTPS/TLS, SLA, RTO
- systemd, UFW, fail2ban, gpg, rclone
- Hard cap, Cooldown

---

## Приложение Е. Процесс работы нескольких AI-агентов

Формализует роли и взаимодействие между Claude, Claude Code, Codex CLI и ChatGPT.

### Е.1. Роли

| Агент | Где | Роль |
| --- | --- | --- |
| Claude (web-чат) | claude.ai | Архитектор, авторский надзор, ревью, изменения ТЗ |
| ChatGPT (web) | chatgpt.com | Второй планирующий слой, оценка решений |
| Claude Code | `~/duzman` на VPS | Исполнитель кода под Anthropic skills |
| Codex CLI | `~/duzman` на VPS | Исполнитель кода под OpenAI sandbox policy |

### Е.2. Источник правды

Единственный источник правды — текущая версия ТЗ (на момент 19 мая 2026 это v1.7, файл `docs/TZ.md` в репозитории).

Все агенты при старте задачи читают `docs/TZ.md`. Подробный change-control процесс описан в разделе 0.4. Отклонения от ТЗ не допускаются (см. раздел 0.4).

### Е.3. Конвенции для агентов

Конвенции проекта (стиль кода, тесты, безопасность, обновление `docs/ARCHITECTURE.md`) хранятся в двух файлах с идентичным содержанием:

- `.claude/skills/duzman-conventions/SKILL.md` — читается Claude Code автоматически
- `AGENTS.md` в корне репозитория — читается Codex CLI автоматически

При любом изменении конвенций обновляются оба файла.

### Е.4. Защита от конфликтов

- Git как точка синхронизации. Исполнитель работает в выделенной
  feature branch вида `pr-<issue-short-name>`. Push в feature branch
  исполнителем разрешён при одобренном Issue. Push в main и любые
  protected branches запрещён. Merge в main — только через PR с
  прохождением reviewer-agent проверки и одобрением Operator.
- Не запускать двух агентов одновременно на одном файле или модуле
- Если параллельная работа нужна — явное разделение зон. Например: Claude Code = коллекторы, Codex = API. Не наоборот
- `docs/ARCHITECTURE.md` обновляется любым агентом в конце задачи. Перед началом работы агент читает `docs/ARCHITECTURE.md`

### Е.5. Протокол передачи между сессиями

В конце сессии исполнитель:

- Обновляет `docs/ARCHITECTURE.md` (что изменилось в архитектуре)
- Делает git commit с осмысленным message
- Push в feature branch
- Открывает PR (если задача завершена) с заполненным телом по
  docs/AGENT_PROTOCOL.md (ссылка на Issue, отчёт по Definition
  of done, явное указание зоны спецификации, отчёт верификации)
- Если изменения требуют обновления конвенций — обновляет ОБА файла (`SKILL.md` и `AGENTS.md`)

В начале сессии исполнитель:

- `git checkout main && git pull`
- Создаёт новую feature branch от свежего main под одобренный Issue
- Читает `docs/TZ.md` (ТЗ)
- Читает `docs/ARCHITECTURE.md` (текущее состояние)
- Читает свой файл конвенций (`SKILL.md` или `AGENTS.md`)
- Читает Issue и спецификацию задачи (формат — Приложение Г, 8 полей)

### Е.6. Когда обращаться к Claude через web-чат

- Архитектурные решения с trade-offs
- Когда coding agent не справился за 2-3 итерации
- Code review подозрительных diff
- Нестандартные баги
- Изменения в ТЗ (всегда через Claude в web-чате, итог — новая версия документа)
- Конфликты между Claude Code и Codex
- Reviewer-agent вернул REQUEST_CHANGES или NEEDS_TZ_UPDATE и
  причина не очевидна

### Е.7. Ограничения по агентам

Полный список общих и роль-специфичных forbidden actions — см.
Приложение Ж.

### Е.8. Спорные ситуации

Если Claude Code и Codex дают разные рекомендации по одной задаче — решение принимает Operator после консультации с Claude (web-чат).

Если ChatGPT и Claude дают разные рекомендации — Operator выбирает на основе аргументации. Финальное решение фиксируется в `docs/ARCHITECTURE.md` или в ТЗ (если архитектурное).

Полная процедура разрешения конфликтов — см. Приложение Ж.4.

---

## Приложение Ж. Роли агентов и forbidden actions

Новое в v1.7. Нормативный справочник ролей и запретов.

### Ж.1. Общие forbidden actions

Применяется ко всем агентам-исполнителям (Claude Code, Codex CLI),
если явно не указано иное в одобренном Issue:

- Push в main или любую protected branch напрямую. Разрешён
  только push в выделенную feature branch при одобренном Issue
- Любые изменения git remote
- Чтение или модификация .env, ~/.ssh/*, любых credential-файлов,
  токенов, shell profiles
- sudo, apt, systemctl
- chmod, chown без явного одобрения Operator
- Доступ к /opt/duzman
- alembic upgrade против production БД
- Прямые DDL или DML через psql против production БД
- Изменения файлов вне объявленной "Зоны спецификации"
- Удаление миграций, файлов в docs/archive/, docs/specs/,
  исторических записей CHANGELOG.md
- Live external API calls в тестах
- Любая trading, order, account или private-key логика

### Ж.2. Роли

| Роль | Где работает | Что делает | Что НЕ делает | Отчёт |
|------|--------------|------------|----------------|-------|
| Operator | desktop, SSH, web-чат | Решения, scope, merge, deploy, разрешение конфликтов, ведение CHANGELOG.md и docs/ARCHITECTURE.md через свои коммиты, emergency и manual fixes | Не является штатным исполнителем agent workflow; обычная реализация идёт через Issue/PR | Не требуется |
| Claude web | claude.ai | Архитектура, написание ТЗ и спек (формат Приложения Г), code review через web_fetch публичного репо, change-control по 0.4 | Не выполняет код на VPS, не пушит | Спецификации и ревью-комментарии в чат |
| ChatGPT web | chatgpt.com | Second opinion на архитектурные решения по запросу Operator, черновики и критика спек | Не меняет репозиторий напрямую | Свободный формат |
| Claude Code | ~/duzman на VPS | Исполнение спек, тесты, рефакторинг внутри зоны спецификации, открытие feature branch и PR | Ж.1 плюс: не пишет ТЗ, не пишет спеки | По docs/AGENT_PROTOCOL.md (Definition of done): diff, тесты, чек-лист критериев готовности, хеш коммита, обновлённый docs/ARCHITECTURE.md, ссылка на PR |
| Codex CLI | ~/duzman на VPS | Исполнение спек, тесты, типизированные модули | Ж.1 плюс: не делает архитектурных решений, не правит несколько модулей в одной задаче | То же что Claude Code |
| Reviewer agent | claude.ai с web_fetch публичного репо | Ревью PR против связанного Issue, docs/TZ.md, AGENTS.md/SKILL.md, diff и отчёта верификации | Не пишет код, не мержит | Вердикт APPROVE / REQUEST_CHANGES / REJECT_SCOPE_VIOLATION / NEEDS_TZ_UPDATE с обоснованием |

Вердикты reviewer-agent:

- APPROVE: diff внутри объявленной зоны спецификации, критерии
  готовности выполнены, отчёт верификации соответствует. PR
  готов к merge Operator-ом
- REQUEST_CHANGES: diff внутри зоны, но есть замечания по
  реализации, тестам, документации или отчёту. Исполнитель
  дорабатывает PR в той же ветке
- REJECT_SCOPE_VIOLATION: diff содержит файлы вне объявленной
  "Зоны спецификации" без явного одобрения Operator. PR
  закрывается или возвращается на серьёзную переработку
- NEEDS_TZ_UPDATE: реализация корректна, но выявила
  противоречие или пробел в docs/TZ.md. PR не принимается как
  обычная задача; требуется отдельный change-control PR
  по 0.4 (либо откат изменения, либо обновление ТЗ)

### Ж.3. Эскалация

Исполнитель обязан остановиться и эскалировать в web-чат с
Operator (или с Claude web), если:

- Требуемое изменение выходит за объявленную зону спецификации
- docs/TZ.md противоречит текущему коду или docs/ARCHITECTURE.md
- Тесты остаются красными после двух фокусированных итераций
- Реализация требует секретов, live DB, deploy, sudo/systemd,
  доступа к production или API credentials
- Задача требует менять архитектуру за пределами одобренного
  Issue
- Связанный Issue или спека не содержит критериев готовности
  или зоны спецификации

### Ж.4. Разрешение конфликтов

Если Claude Code, Codex CLI, ChatGPT, Claude web и reviewer-agent
дают расходящиеся рекомендации — финальное решение принимает
Operator.

Если решение меняет архитектуру или процесс — оно фиксируется:
- В docs/TZ.md, если изменение архитектурное или процессное
  (через change-control по 0.4)
- В docs/ARCHITECTURE.md, если изменение только архитектурное и
  не требует обновления ТЗ

---

## Заключение

Версия 1.7 формализует GitHub-based multi-agent workflow и change-control процесс. Включает все уточнения версий 1.3 — 1.6.

После завершения этапа А и периода эксплуатации не менее 30 дней принимается решение о переходе к этапу Б.

### Контроль версий

| Версия | Дата | Описание |
| --- | --- | --- |
| 1.0 | 12 мая 2026 | Внутренний draft по секциям 1-7 |
| 1.1 | 13 мая 2026 | Первая полная консолидированная версия |
| 1.2 | 13 мая 2026 | После аудита. Hard caps, граница А/Б, Spec format, Глоссарий |
| 1.3 | 16 мая 2026 | После дней 1-3. Разделение dev/prod, процесс изменения ТЗ, ingestion endpoints, runtime модуль, переструктуризация дней 3-4, мультиагентный workflow (Приложение Е) |
| 1.4 | 17 мая 2026 | Перед днём 6. Расщепление А.3/А.4 в Приложении А на _majors/_alts (10 шаблонов вместо 8). Переписан раздел 4.6 (явная трёхуровневая иерархия cooldown / soft cap 3/час / hard cap 10/час / hard cap 30/сутки). Уточнения по dev/prod в 0.3 (duzman vs duzman_app, общая БД для dev/prod) |
| 1.5 | 17 мая 2026 | Перед Спекой 4 дня 6 (AlertGate). Раздел 4.6 дополнен явным порядком проверок (cooldown -> daily hard cap -> hourly hard cap -> soft cap) и определением источника правды для счётчиков (только ALLOW; на дне 6 — через pattern_triggers.conditions_snapshot.gate_decision; на дне 7 — через alerts_sent). Раздел 7.7 и Приложение Б синхронно дополнены |
| 1.6 | 18 мая 2026 | Перед началом реализации Спеки 4 дня 6 (AlertGate). Раздел 4.6 и 7.7 уточнены: дефолт `cooldown_hours = 2 часа` реализуется в Pydantic-модели `PatternDefinition` (`src/duzman/patterns/models.py`) на этапе загрузки конфигурации, AlertGate собственного fallback не имеет. Других изменений нет |
| 1.7 | 19 мая 2026 | Формализация GitHub-based multi-agent workflow. Раздел 0.4 переписан как change-control. Добавлен раздел 0.5 (GitHub как транспорт между агентами). Приложение Г расширено до 8 полей (добавлена "Зона спецификации"). Приложение Е обновлено под Issue/PR workflow. Добавлено Приложение Ж (роли и forbidden actions, четыре вердикта reviewer-agent). Синхронные апдейты AGENTS.md и .claude/skills/duzman-conventions/SKILL.md. Docs-only, продуктовые контракты не затронуты |
