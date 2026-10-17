# Как участвовать в `terminal-browser`

## Что это за проект

`terminal-browser` — ограниченный образовательный текстовый HTTP/1.1-браузер. Его цель — показать явную архитектуру, детерминированные ограничения и проверяемую инженерную работу, а не предоставить универсальный браузер. (§1, §2.3)

Перед предложением работы прочитай `ARCHITECTURE.md`. Архитектура — источник истины, а намеренные границы скоупа зафиксированы в §12. (§2.3, §12)

## Прежде чем открывать что-либо

Начни с `ARCHITECTURE.md`, locked decisions, non-goals, module graph и Deliberate Deviations. Отсутствующая функция может быть намеренной границей, а не упущением. (§1, §2, §12)

## Что приветствуется

- Bug reports, когда поведение противоречит `ARCHITECTURE.md`, с минимальным воспроизведением и указанием нарушенного раздела. (§1–§12)
- Исправления документации, битые relative links и расхождения EN/RU. (process constraint в `CLAUDE.md`)
- Regression tests для архитектурного поведения без требуемого покрытия. (§10.9)

## Что вне скоупа

- Фичи, расширяющие locked browser scope без обновления архитектуры. (§1 N1–N10, §2.3, §12)
- JavaScript, CSS, image bytes, HTTP/2, WebSocket, `iframe`, authentication/proxy, Brotli/zstd, keep-alive pooling и cookie-domain widening. (§1 N1–N10, §12 DD-01–DD-10, DD-21)
- Зависимости вне архитектурной runtime boundary Pydantic v2. (§2.3 R7, R8)

## Workflow: по одному модулю

1. Выбери один модуль из порядка сборки §11.
2. Реализуй только этот модуль и непосредственно требуемое поведение.
3. Остановись после модуля; не переходи молча к следующему. (§11)
4. Добавь требуемые тесты модуля из матрицы §10.9. (§10.9)
5. Добавь AST import-boundary test, доказывающий, что модуль импортирует только зависимости, разрешённые §2.2. (§2.2, §10.9)
6. После модуля запусти `pytest -v` и `mypy --strict` и сохрани полный сырой terminal output. (§11, `CLAUDE.md`)

## Правила доказательств

Raw evidence — это полный command output `pytest -v` от `collecting ...` до финального test summary и полный output явной команды `mypy --strict`. Summary, paraphrase, screenshot, truncated paste или выбранное подмножество доказательствами не являются. (§11, `CLAUDE.md`)

Каждый acceptance claim должен называть команду, сохранять полный output и указывать доказанный модуль или требование. (§11, `CLAUDE.md`)

## Имя теста доказывает требование

Имя теста должно описывать доказываемое поведение. Предпочтительны имена вроде `test_failed_navigation_preserves_state`, а не `test_session_2`; имя является частью проверяемых доказательств. (§10.9, process constraint в `CLAUDE.md`)

Тест, который проверяет только type shape, import или happy path, не доказывает atomicity, timeout, security или error-ownership, если assertion явно не демонстрирует это поведение. (§5, §7.3, §10.9)

## Сеть и изоляция тестов

Тесты не должны обращаться к реальной сети. Используй local socket fixtures, scripted transports, fake clocks и injected output buffers. (§1 G9, §10.3–§10.5, `CLAUDE.md`)

Не добавляй public-network integration test вместо deterministic fixture. (§1 G9, §10.3–§10.5)

## Deviations

Перед изменением locked decision запиши предложенное отклонение, техническое обоснование, затронутые разделы и approval status в `ARCHITECTURE.md` §12. Не реализуй deviation первым и не документируй его потом. (§2.3, §12)

DD-13 — DNS-resolution deviation от locked decision #8; архитектура сейчас помечает approval как required. (§12 DD-13)

## Review checklist

Перед запросом review проверь:

- изменение касается одного модуля или одного явно документированного deviation; (§11, §12)
- существуют требуемые тесты и AST boundary tests; (§10.9)
- приложен raw output `pytest -v` и `mypy --strict`; (§11)
- реальная сеть не использовалась; (§1 G9, §10.3–§10.5)
- при изменении документации EN и RU остаются полными зеркалами. (process constraint в `CLAUDE.md`)

## Лицензия

Вклад распространяется по [MIT License](LICENSE).
