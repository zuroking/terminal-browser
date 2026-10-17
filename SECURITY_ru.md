# Политика безопасности

> Английская версия: [SECURITY.md](SECURITY.md)

## Scope

`terminal-browser` — ограниченный text browser, а не complete graphical browser. Security claims в этом документе ограничены документированным поведением architecture. (§1, §12)

Подозреваемые уязвимости сообщай приватно через security-reporting channel репозитория, а не в public issue. Укажи affected module, reproduction, expected behavior, actual behavior и relevant architecture section. (process constraint в `CLAUDE.md`)

## Две sanitization checkpoints

Untrusted text очищается при construction и повторно при terminal egress. Construction sanitization защищает parsed page data; egress sanitization защищает финальные terminal bytes. (§4, §5 I1)

Egress test сканирует все production `.py` files под `src/` и исключает только `term/output.py`; отклоняет direct stream access, aliases, `print`, `os.write` и другие imported или opened output streams. (§10.7)

## TLS и network boundaries

TLS certificate и hostname verification безусловны; non-verifying policy не представлена. (§5 I2, §3.6)

Каждый socket read имеет explicit byte bound и per-`recv` timeout. DNS, redirects, response bodies и whole navigation имеют отдельные bounded deadlines. (§5 I3, I5, §6, §9.2, §9.4)

Decompression проверяется после каждого inflater output chunk и не может создать unbounded allocation. (§5 I6, §6, §9.3)

DNS resolution использует документированный DD-13 deviation: timed daemon worker может оставить OS resolver call живым после navigation timeout, хотя worker не владеет socket и не может отправить request. (§9.9, §12 DD-13)

## Cookies и forms

Cookies host-only; cookie `Domain=` widening игнорируется. (§1 N10, §9.6, §12 DD-10)

Password field values никогда не render-ятся, поэтому saved-page или REPL output не раскрывает value. (§8.5, §8.7, §12 DD-15)

POST-created history entries replay-ятся как GET без original body и с sanitized notice. (§9.7, §12 DD-18)

## Вне скоупа

Документированные non-goals не являются security bugs: JavaScript, CSS, image bytes, HTTP/2, WebSocket, `iframe`, authentication/proxy, Brotli/zstd, keep-alive pooling и cookie-domain widening. (§1 N1–N10, §12)

Reader не обещает защиту от attacker, который уже контролирует process, operating system или local input environment; эти угрозы вне bounded reader model. (§1, §12)

## Проверка

Security behavior покрыта per-module test matrix, включая transport TLS failures, bounded reads, sanitizer invariants, host-only cookies, password rendering и AST egress test. (§10.9)
