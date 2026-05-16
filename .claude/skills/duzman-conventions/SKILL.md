---
name: duzman-conventions
description: Конвенции проекта Duzman. Применять автоматически при любой работе в репозитории duzman. Включает: src-layout, стиль docstrings, требования к тестам (pytest, async, моки), безопасность, обязательное обновление ARCHITECTURE.md в конце каждой задачи, разделение dev (~/duzman) и prod (/opt/duzman).
---

# Duzman project conventions

Этот SKILL.md читается автоматически Claude Code при работе в репозитории Duzman. Идентичная копия для Codex CLI лежит в `AGENTS.md` в корне репо. При любом обновлении конвенций — обновляются оба файла.

## 1. Источник правды

Единственный источник правды для всех задач — `docs/TZ.md` (текущая версия технического задания).

- Перед любой задачей: прочитать `docs/TZ.md` целиком, либо релевантную секцию
- Отклонения от ТЗ не допускаются. Если обнаружено что ТЗ требует доработки — остановиться, описать проблему, ждать решения Operator
- ТЗ обновляется только Operator-ом через web-чат с Claude. Не редактировать `docs/TZ.md` напрямую

## 2. Архитектурные правила

- src-layout: весь Python-код в `src/duzman/`
- Editable install: `.venv/bin/python -m pip install -e .`
- Виртуальное окружение только проектное (`.venv/`), не глобальное
- Никаких глобальных установок через `pip install`, `pip install --user`, `sudo apt install python-*`
- ORM: SQLAlchemy 2.0. Миграции: Alembic
- Async: httpx.AsyncClient для HTTP, asyncio.gather для параллельного сбора
- Структура модулей по ТЗ раздел 6.3

## 3. Конвенции кода

### Docstrings
- Module-level docstring обязателен в каждом `.py` файле
- Class docstring обязателен
- Public function/method docstring обязателен
- Format: краткое описание одной строкой, при необходимости пустая строка и подробности
- Указывать типы аргументов и возвращаемых значений через type hints, не в docstring

### Импорты
- Стандартная сортировка: stdlib → third-party → local
- Абсолютные импорты от `duzman.*`, не относительные

### Логирование
- structlog с safe event names
- НЕ логировать: raw payloads, query parameters, секреты, `DATABASE_URL`, env переменные
- Логировать: event name, asset, source, status, latency_ms, bounded error message

## 4. Тесты

- pytest, async через `pytest-asyncio`
- Все HTTP — моки через httpx mock transport или responses lib
- НЕ запускать живые API в тестах (ни Binance, ни Bybit, ни Anthropic)
- Тесты не требуют `DATABASE_URL`, `.env` или живого PostgreSQL
- Coverage: success path, timeout, partial failure, schema validation

## 5. Безопасность

### Что запрещено всегда
- `sudo`, `apt`, `systemctl`, `chmod`, `chown`, `ufw`, `fail2ban-client`
- `git push` (push выполняет только Operator вручную)
- `git remote` без отдельной задачи
- Чтение `.env`, `~/.ssh/id_*`, `~/.bashrc`, `~/.profile`
- `psql`, `createdb`, `dropdb`, `alembic upgrade` без отдельной задачи
- `env`, `printenv` (могут содержать секреты)
- Установка глобальных env переменных `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `DATABASE_URL`

### Что требует осторожности
- `rm -rf` — только с явным подтверждением Operator
- Любая работа с production директорией `/opt/duzman` — запрещена. Работаем только в `~/duzman`

### Секреты в коде и доках
- Никаких реальных паролей, ключей, токенов в коде, тестах, доках, логах
- Только placeholder `REPLACE_WITH_PASSWORD`, `your-api-key-here` и т.п.
- Реальные секреты — только в `/opt/duzman/.env` с правами 600, читает только пользователь `duzman`

## 6. Документация

### ARCHITECTURE.md
- Обновляется в конце каждой задачи. Это обязательное правило, не опциональное
- Содержит: текущее состояние модулей, какие компоненты работают, какие в процессе, какие ещё не начаты
- Краткие записи, не дублирующие ТЗ

### CHANGELOG.md
- Краткая запись после каждого коммита: что изменено, для какой задачи
- Format: `[дата] [тип: feat/fix/docs/refactor] описание`

### Docstrings и комментарии
- На английском (стандарт open-source)
- ARCHITECTURE.md, CHANGELOG.md, README.md — на английском
- Commit messages — на английском

## 7. Git workflow

### Каждая сессия
- Начало: `git pull`
- Конец: `git commit` с осмысленным сообщением. Push выполняет Operator вручную

### Размер коммитов
- Один коммит = одна логическая задача
- НЕ собирать всё в один большой коммит за день
- Commit message формат: краткая строка (50 символов), пустая строка, детали при необходимости

### Что НЕ коммитить
- `.env`, `.env.local`, любые файлы с секретами
- `.venv/`, `__pycache__/`, `.pytest_cache/`
- Локальные конфиги IDE (`.vscode/`, `.idea/`)
- Большие бинарные файлы

## 8. Стиль работы агента

### Узкие задачи
- Одна задача = одна спецификация по формату Приложения Г в ТЗ
- НЕ брать «сделай всё что нужно для дня X». Брать «реализуй BinanceCollector»
- Если задача шире одного коммита — разбить на подзадачи

### Когда останавливаться и спрашивать
- ТЗ требует доработки или содержит противоречие
- Задача выходит за рамки ТЗ
- Зацикливание (2-3 итерации без прогресса)
- Подозрение на конфликт с другим агентом (свежий неожиданный diff в `git status`)
- Запрос требует sudo, push, доступа к `/opt/duzman` или секретам

### Обновление этого файла
- Если в процессе работы обнаружено что конвенция требует уточнения или изменения — внести правку в `.claude/skills/duzman-conventions/SKILL.md` и одновременно в `AGENTS.md`
- Описать изменение в commit message

## 9. Разделение зон между агентами

При параллельной работе Claude Code и Codex CLI Operator явно указывает зону ответственности (например: «Codex работает в `src/duzman/collectors/`, Claude Code — в `src/duzman/api/`»). Без явного разделения параллельная работа не ведётся.

## 10. Production deployment

- Production директория: `/opt/duzman`, пользователь `duzman`, без sudo
- Разработка: `~/duzman`, пользователь `ubuntu`
- Deploy: ручной скрипт `scripts/deploy.sh` (день 9), копирует код из `~/duzman` в `/opt/duzman`
- AI agents НЕ имеют доступа к `/opt/duzman`. Работают только в `~/duzman`
