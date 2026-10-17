# PROTOCOL_ru.md

## Назначение

Документ задаёт проверяемый workflow для `terminal-browser`. Это процессный контракт, а не замена `ARCHITECTURE.md`; архитектура остаётся источником истины. (§2.3, §11)

## Роли

- **Owner:** задаёт scope, принимает финальные архитектурные решения, approves deviations и принимает evidence модуля. (§12)
- **Implementer:** реализует по одному модулю в порядке §11, пишет тесты и создаёт raw evidence. (§11, process constraint в `CLAUDE.md`)
- **Architectural reviewer:** проверяет согласованность с locked architecture, оспаривает implicit assumptions и отклоняет unsupported или incomplete evidence. (§1, §12, process constraint в `CLAUDE.md`)

Роли не взаимозаменяемы: implementer предлагает и строит, reviewer проверяет, owner решает. (process constraint в `CLAUDE.md`)

## Правила доказательств

Только raw, complete terminal output является доказательством:

- `pytest -v` должен содержать полный прогон от `collecting ...` до финального summary `N passed`.
- `mypy --strict` должен содержать точную команду и полный output.
- Summary, paraphrase, screenshot, selected test subset или truncated paste отклоняются. (§11, process constraint в `CLAUDE.md`)

Каждый claim должен называть command, complete output и module или requirement, который он доказывает. (§11, process constraint в `CLAUDE.md`)

## Имя теста доказывает требование

Имя теста должно описывать проверяемое поведение. Имя `test_failed_navigation_preserves_state` является более сильным доказательством, чем generic или implementation-only имя. (§10.9, process constraint в `CLAUDE.md`)

Тест должен assert-ить named requirement. Happy-path test не доказывает timeout enforcement, atomic history, security sanitization или exception propagation, если эти условия не assert-ятся явно. (§5, §7.3, §10.9)

## Правило batching

Работа batching-ится только по leaf modules. Module реализуется после перечисленных dependencies, затем implementation останавливается до review его tests, boundary test и raw evidence. (§11)

Dependency order — это build order §11; удобство его не переопределяет. (§2.3, §11)

## Правило AST import-boundary

Каждый production module получает AST-based test, доказывающий соответствие direct imports dependency graph. Тест сканирует source syntax, а не полагается на text grep. (§2.2, §10.9)

Egress test дополнительно сканирует каждый production `.py` file и исключает только `term/output.py`. (§10.7)

## Calibration incidents

### Incident #1 — `net/wire.py`

Вставленный результат `pytest -v` был неполным: в нём отсутствовало начало или конец прогона. Его отклонили outright, потому что incomplete paste не доказывает запуск полного required suite. (§10.5, §11, process constraint в `CLAUDE.md`)

Required response: повторить command и сохранить complete raw output от `collecting ...` до final summary. (§11, process constraint в `CLAUDE.md`)

### Incident #2 — `net/cookies.py`

Tie-break test отклонили, потому что его имя и assertion не закрепляли required sequence-before-name rule. Проходящий тест, не доказывающий requirement, доказательством не является. (§9.6, §10.9, process constraint в `CLAUDE.md`)

Required response: переименовать и усилить тест так, чтобы deterministic ordering rule была явно указана в имени и assertion. (§9.6, §10.9)

## Review loop

1. Прочитать applicable locked decision и architecture section.
2. Реализовать один module в dependency order.
3. Добавить required tests и AST boundary test.
4. Запустить full `pytest -v` и explicit `mypy --strict` commands.
5. Приложить complete raw output.
6. Остановиться для architectural review.
7. Записать approved deviation в §12 до изменения implementation. (§11, §12)

## Documentation review

EN и RU документы являются зеркалами: одинаковые sections, order, facts и citations. Templates задают только style; факты поставляет `ARCHITECTURE.md`. (task constraint; process constraint в `CLAUDE.md`)
