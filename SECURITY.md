# Security Policy

> Russian version: [SECURITY_ru.md](SECURITY_ru.md)

## Scope

`terminal-browser` is a bounded text browser, not a complete graphical browser. Security claims in this document are limited to the architecture's documented behavior. (§1, §12)

Report suspected vulnerabilities privately through the repository's security-reporting channel rather than a public issue. Include the affected module, reproduction, expected behavior, actual behavior, and relevant architecture section. (process constraint in `CLAUDE.md`)

## Dual sanitization checkpoints

Untrusted text is sanitized at construction time and again at terminal egress. Construction sanitization protects parsed page data; egress sanitization protects the final terminal bytes. (§4, §5 I1)

The egress test scans all production `.py` files under `src/` and excludes only `term/output.py`; it rejects direct stream access, aliases, `print`, `os.write`, and other imported or opened output streams. (§10.7)

## TLS and network boundaries

TLS certificate and hostname verification are unconditional; a non-verifying policy is not represented. (§5 I2, §3.6)

Every socket read has an explicit byte bound and a per-`recv` timeout. DNS, redirects, response bodies, and the whole navigation have separate bounded deadlines. (§5 I3, I5, §6, §9.2, §9.4)

Decompression is checked after each inflater output chunk and cannot create an unbounded allocation. (§5 I6, §6, §9.3)

DNS resolution uses the documented DD-13 deviation: a timed daemon worker may leave the OS resolver call alive after navigation timeout, although that worker owns no socket and cannot issue a request. (§9.9, §12 DD-13)

## Cookies and forms

Cookies are host-only; cookie `Domain=` widening is ignored. (§1 N10, §9.6, §12 DD-10)

Password field values are never rendered, which prevents saved-page or REPL output from disclosing the value. (§8.5, §8.7, §12 DD-15)

POST-created history entries are replayed as GET without the original body and with a sanitized notice. (§9.7, §12 DD-18)

## Out of scope

The documented non-goals are not security bugs: JavaScript, CSS, image bytes, HTTP/2, WebSockets, `iframe`, authentication/proxy, Brotli/zstd, keep-alive pooling, and cookie-domain widening. (§1 N1–N10, §12)

The reader does not promise protection from an attacker who already controls the user's process, operating system, or local input environment; those threats are outside the bounded reader model. (§1, §12)

## Verification

Security behavior is covered by the per-module test matrix, including transport TLS failures, bounded reads, sanitizer invariants, host-only cookies, password rendering, and the AST egress test. (§10.9)
