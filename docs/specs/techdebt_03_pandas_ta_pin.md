# techdebt_03: pin pandas-ta version

Based on: Техническое задание v1.7 от 2026-05-19 (docs/TZ.md)

## Issue

Closes #10

## Контекст

В pyproject.toml зависимость `pandas-ta` указана без версии. Это нарушает воспроизводимость сборки: при пересоздании venv с нуля может приехать другая версия с другим API/поведением индикаторов, что незаметно сломает сравнения, тесты и продовые алерты.

Текущая установленная версия в dev venv — `0.4.67b0` (pre-release). Закрепляем её точно через `==` как проверенную рабочую.

Скоуп ограничен только `pandas-ta`. Остальные зависимости из `[project].dependencies` без пина (aiosqlite, beautifulsoup4, lxml) в эту задачу НЕ входят.

## Зона спецификации

- pyproject.toml

Файлы вне этого списка изменяться не должны.

## Что нужно сделать

В pyproject.toml в массиве `[project].dependencies` заменить строку

```
    "pandas-ta",
```

на

```
    "pandas-ta==0.4.67b0",
```

Остальные строки в `dependencies` и `[project.optional-dependencies].dev` не трогать. Версии других пакетов не менять.

## Definition of done

- [ ] В pyproject.toml в `[project].dependencies` присутствует строка `"pandas-ta==0.4.67b0",`.
- [ ] В pyproject.toml нет строки `"pandas-ta",` без версии.
- [ ] Остальные строки `[project].dependencies` (aiosqlite, beautifulsoup4, lxml) не изменены.
- [ ] Блок `[project.optional-dependencies]` не изменён.
- [ ] Других файлов PR не трогает.
- [ ] Тесты зелёные: `.venv/bin/python -m pytest -q`.

## Проверки

```
grep -n "pandas-ta" pyproject.toml
```
Ожидается: ровно одна строка вида `    "pandas-ta==0.4.67b0",`.

```
grep -nE '^\s*"pandas-ta",\s*$' pyproject.toml
```
Ожидается: пусто (старой строки без версии нет).

```
.venv/bin/pip show pandas-ta | grep Version
```
Ожидается: `Version: 0.4.67b0` (установленная версия совпадает с пином, переустановка не требуется).

```
git diff --stat
```
Ожидается: изменён только pyproject.toml, 1 строка добавлена, 1 удалена.

```
.venv/bin/python -m pytest -q
```
Ожидается: 268 passed.

## Ветка и PR

- Ветка: `techdebt/10-pandas-ta-pin`
- Заголовок PR: `build: pin pandas-ta to 0.4.67b0 (#10)`
- Тело PR заполнить по шаблону, в Definition of done и Проверки скопировать пункты из этой спеки.

## Forbidden actions

Стандартный набор из Приложения Ж docs/TZ.md. Дополнительно:
- НЕ менять версии других пакетов в pyproject.toml.
- НЕ менять секцию `[project.optional-dependencies]`.
- НЕ запускать `pip install --upgrade` или `pip install -e .` и не пересоздавать venv (текущая установленная версия уже совпадает с целевым пином).
- НЕ менять никакие файлы кроме pyproject.toml.
