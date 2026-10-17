# Журнал изменений

Здесь фиксируются все значимые изменения `terminal-browser`. Записи следуют зафиксированному порядку сборки из `ARCHITECTURE.md` §11 и описывают завершённую реализацию, а не будущий roadmap. (§11)

## [2.0.0] — 2026-09-24

Завершённая реализация v2 содержит все 21 модуль в порядке сборки из архитектуры. (§11)

### Добавлено

- `core/errors.py`: единственный корень исключений `BrowserError` и frozen strict `ErrorInfo`. (§3.1, §7)
- `core/limits.py`: frozen strict resource limits и проверка cross-cap ограничений. (§3.2, §6)
- `core/clock.py`: seam часов monotonic/epoch с `SystemClock` и детерминированным `FakeClock`. (§3.3, §10.4)
- `core/encoding.py`: ограниченное определение charset и декодирование с replacement. (§3.4, §8.2)
- `core/sanitize.py`: очистка текста и атрибутов при построении. (§3.5, §4)
- `core/text.py`: общая политика display width в ячейках терминала. (§3.6, §8.6)
- `url.py`: parsing HTTP(S), IDNA/IPv6, relative resolution и узкая cache normalization. (§3.9, §8.1)
- `net/transport.py`: ограниченные socket, TLS, DNS, connect и read transport. (§3.6, §3.10, §10.3)
- `net/wire.py`: чистые parsing status, header, chunk и trailer для HTTP/1.1. (§3.7, §9.4, §10.5)
- `net/cookies.py`: host-only cookie jar с часами, ограниченным eviction и send ordering. (§3.8, §9.6)
- `net/cache.py`: ограниченный LRU и disk cache с validators и HTTP cache directives. (§3.9, §9.5, §10.6)
- `net/http.py`: request framing, redirects, deadlines, cookies, cache, decoding и response dispatch. (§3.10, §9.1–§9.5)
- `html/entities.py`: entities в стиле HTML4 плюс `apos`, numeric references и context rules. (§3.11, §8.4)
- `html/tokenizer.py`: инкрементальный lazy tokenizer с lexical modes и hard token caps. (§3.12, §8.4)
- `html/tree.py`: ограниченный DOM builder, recovery, base/link resolution, sanitization и видимая truncation. (§3.12, §8.3–§8.4)
- `forms.py`: extraction форм, successful controls, labels, GET/POST serialization и limits. (§3.14, §8.5)
- `render/layout.py`: детерминированный width-aware text layout, links, forms, tables и truncation notices. (§3.13, §8.6–§8.9)
- `term/output.py`: единственный владелец stdout/stderr с construction/egress defense in depth. (§3.13, §4, §10.7)
- `session/session.py`: navigation pipeline, atomic history, forms, BrowserError views и POST replay. (§3.15, §7.3, §9.7–§9.8)
- `ui/repl.py`: ограниченный line REPL, command dispatch, width resolution и обработка exit. (§3.16, §10.1)
- `cli.py`: argument parsing, dependency composition, one-shot/interactive modes, exit codes и top-level catch-all. (§3.16, §7.3, §10.2)
- Нормативное AST-покрытие egress: `tests/test_egress.py` сканирует production Python files и исключает только `term/output.py`. (§10.7)

### Изменено

- Исправление v1 для cache key сохраняет query bytes byte-for-byte, включая order, duplicates, percent-escape spelling и case. (§8.1)
- Исправление v1 для cacheability делает любой response с `Vary` non-cacheable. (§9.5)
- Полный локальный suite зелёный: прошли `390` тестов; strict mypy чист. (§10.9, §11; repository verification)

### Исправлено

- Terminal egress test теперь отклоняет `print`, прямой доступ к standard streams и их aliases, `os.write`, а также imported или opened output streams вне `term/output.py`. (§10.7)
- Финальная CLI boundary сохраняет `KeyboardInterrupt` как exit code `130`, повторно выбрасывает `SystemExit` и очищает debug traceback. (§7.3, §10.2)

### Запись о deliberate deviation

- DD-13 зафиксирован в истории процесса как одобренный в этой сессии для продолжения реализации. `ARCHITECTURE.md` всё ещё помечает DD-13 как `[APPROVAL REQUIRED]`, поэтому перед полным синхронизированием требуется архитектурная сверка. (§12 DD-13)

### Проверка

- Полное test evidence: `390 passed`. (§10.9, §11)
- Type evidence: `mypy --strict` прошёл для финальной реализации и тестов. (§11)
