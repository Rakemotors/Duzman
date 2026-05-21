# Review Protocol

Этот протокол описывает review PR по workflow TZ v1.7, Приложение Ж.
Reviewer проверяет PR против связанного Issue, docs/TZ.md, AGENTS.md или
SKILL.md, diff и отчёта верификации в теле PR.

## Роли

- Автор PR (агент): Claude Code или Codex CLI, который выполняет одобренное
  Issue внутри объявленной Зоны спецификации и прикладывает Definition of done.
- Reviewer: Claude web, Claude MCP, reviewer-agent или
  человек, который проверяет scope, DoD, тесты, forbidden
  actions и необходимость обновления TZ. Reviewer agent —
  абстрактная роль; конкретный инструментальный режим
  (Claude web через web_fetch, Claude MCP через GitHub
  connector, или другой) выбирает Operator на сессию.
  Содержательные требования к review одинаковы независимо
  от режима. Дополнительные ограничения режима Claude MCP —
  docs/TZ.md Приложение Ж, раздел Ж.1.1.

## Что проверяет reviewer

- Связанный Issue указан и содержит 8 полей Приложения Г TZ v1.7.
- Diff находится внутри объявленной Зоны спецификации.
- Definition of done из Issue перенесён в PR и отмечен PASS/FAIL.
- Проверки из Issue и PR выполнены, а блокирующие проверки зелёные.
- Forbidden actions из TZ v1.7 Приложение Ж не нарушены.
- Изменение не требует предварительного обновления docs/TZ.md.

## Вердикты

### APPROVE

Применяется, когда Definition of done выполнен, diff не выходит за Зону
спецификации, блокирующие проверки зелёные, отчёт верификации достаточен, а
обновление docs/TZ.md не требуется.

### REQUEST_CHANGES

Применяется, когда PR остаётся внутри Зоны спецификации, но есть замечания по
реализации, документации, тестам, локальным проверкам или полноте отчёта.
Автор дорабатывает PR в той же feature branch.

### REJECT_SCOPE_VIOLATION

Применяется, когда diff содержит изменения вне заявленной Зоны спецификации и
нет явного одобрения Operator. Такой PR нельзя принимать как обычную доработку;
он закрывается или возвращается на серьёзную переработку scope.

### NEEDS_TZ_UPDATE

Применяется, когда реализация выглядит корректной, но задача выявила пробел,
противоречие или новое правило, требующее предварительного change-control PR в
docs/TZ.md. Текущий PR не мержится до решения Operator по TZ.

## Шаблон комментария-вердикта

```text
Verdict: APPROVE | REQUEST_CHANGES | REJECT_SCOPE_VIOLATION | NEEDS_TZ_UPDATE

Scope:
- Declared zone:
- Diff status:

Definition of done:
- PASS/FAIL:

Checks:
- pytest:
- ruff:
- mypy:
- grep:

Findings:
- ...

Required action:
- ...
```
