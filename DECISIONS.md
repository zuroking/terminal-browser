# Architecture Decision Records — `terminal-browser`

This is the granular decision log for the locked architecture. `ARCHITECTURE.md` remains the source of truth; this file records the substance of locked decisions #1–#10 and Deliberate Deviations DD-01–DD-21. (§1, §12)

## ADR format

Each record states its status, context, decision, alternatives, and consequences. The source section is shown for every architectural claim. (§1, §12)

---

## ADR-001: No JavaScript execution

**Status:** [LOCKED]  
**Source:** §1 N1, §12 DD-01

### Context
A complete browser would need a JavaScript engine, DOM bindings, and an event loop. (§12 DD-01)

### Decision
Do not execute JavaScript; drop `script` subtrees. (§1 N1, §12 DD-01)

### Alternatives considered
- Full JavaScript runtime — rejected because it exceeds the bounded text-reader scope. (§12 DD-01)

### Consequences
The reader remains deterministic and bounded, but pages that depend on JavaScript cannot become interactive. (§12 DD-01)

## ADR-002: No CSS engine

**Status:** [LOCKED]  
**Source:** §1 N2, §12 DD-02

### Context
A cascade and visual layout engine would dominate the project. (§12 DD-02)

### Decision
Do not implement CSS selection, cascade, colors, or visual layout; output semantic plain text. (§1 N2, §12 DD-02)

### Alternatives considered
- Browser-compatible CSS engine — rejected because it expands the locked scope. (§12 DD-02)

### Consequences
Layout is readable and deterministic, not a visual reproduction of a page. (§12 DD-02)

## ADR-003: Text-only image fallback

**Status:** [LOCKED]  
**Source:** §1 N3, §12 DD-03

### Context
Image fetching, decoding, and raster rendering are outside the text reader. (§1 N3)

### Decision
Use only `img[alt]` text, or `[image]` when no alternative text exists. (§12 DD-03)

### Alternatives considered
- Download and render image bytes — rejected because it exceeds the text-only scope. (§12 DD-03)

### Consequences
Image information can remain readable without image decoding, but visual image content is unavailable. (§12 DD-03)

## ADR-004: Explicit link and history navigation

**Status:** [LOCKED]  
**Source:** §3.15, §9.7, §10.1

### Context
The session needs a bounded, reproducible navigation model rather than an opaque browser history. (§9.7)

### Decision
Maintain one bounded history list and a position pointer; address links and forms by index. (§1 G4, §3.15, §9.7)

### Alternatives considered
- Store unbounded page snapshots — rejected because history is a bounded list of committed final URLs. (§9.7)

### Consequences
Back and forward can be tested and bounded, while old rendered lines are not replayed. (§9.7)

## ADR-005: Bounded deterministic decoding

**Status:** [LOCKED]  
**Source:** §3.4, §6, §8.2

### Context
Malformed bytes and unknown charset labels must not crash navigation. (§3.4, §8.2)

### Decision
Use a bounded charset allowlist, bounded meta prescan, UTF-8 default, and replacement decoding. (§3.4, §8.2)

### Alternatives considered
- Raise on every unknown label — rejected because decoding is required not to raise for charset labels or malformed bytes. (§3.4)

### Consequences
Decoding is deterministic and bounded, with replacement characters possible for malformed input. (§3.4, §8.2)

## ADR-006: Persistent HTTP cache with validators

**Status:** [LOCKED]  
**Source:** §3.9, §9.5

### Context
Repeated navigation should be able to use fresh data and revalidate stale data. (§1 G6, §9.5)

### Decision
Persist bounded GET cache entries with freshness metadata and HTTP validators. (§9.5)

### Alternatives considered
- Memory-only response reuse — rejected because persistence and validator revalidation are explicit locked behavior. (§9.5)

### Consequences
GET responses can be reused and revalidated within byte and freshness limits; POST responses do not enter the cache. (§9.5)

## ADR-007: GET/POST form extraction and submission

**Status:** [LOCKED]  
**Source:** §3.14, §8.5, §9.8

### Context
The text browser must expose basic form controls and deterministic submission. (§1 G3, §8.5)

### Decision
Extract documented controls and serialize forms as GET or POST with bounded encoding. (§3.14, §8.5, §9.8)

### Alternatives considered
- Full browser form semantics — rejected because the locked model is the documented field subset. (§8.5)

### Consequences
Basic forms work by index, while unsupported or multiple-select cases remain explicit deviations. (§8.5, §12 DD-16–DD-20)

## ADR-008: TLS-verified, wall-clock-bounded HTTP/1.1

**Status:** [LOCKED]  
**Source:** §3.6, §3.10, §6, §9.2, §9.4, §12 DD-13

### Context
The network must be bounded, verifiable, and implementable with the standard library. (§1 G1, §2.3 R1, R7–R8)

### Decision
Use HTTP/1.1 over stdlib `socket`, `ssl`, and `zlib`; verify TLS certificates and hostnames and enforce navigation deadlines. (§3.6, §3.10, §9.2)

### Alternatives considered
- High-level HTTP wrappers or HTTP/2 — rejected by the locked dependency and protocol rules. (§2.3 R7–R8, §12 DD-04)

### Consequences
The client has explicit deadlines and verification, with DNS cancellation limited by the approved deviation boundary. (§9.2, §12 DD-13)

## ADR-009: Bounded incremental HTML/DOM pipeline

**Status:** [LOCKED]  
**Source:** §3.11–§3.12, §6, §8.3–§8.4

### Context
HTML parsing must stop work before unbounded token, node, or depth growth. (§1 G2, G7)

### Decision
Use an incremental tokenizer and bounded DOM builder with visible truncation. (§3.11–§3.12, §8.3–§8.4)

### Alternatives considered
- Build a complete DOM before applying limits — rejected because limits must be incremental. (§6, §8.3)

### Consequences
Large documents are bounded and truncation is visible, but incomplete DOM content may be omitted. (§6, §8.3–§8.4)

## ADR-010: Sanitized terminal construction and one egress point

**Status:** [LOCKED]  
**Source:** §3.13, §4, §10.7

### Context
Untrusted text must not inject terminal controls, and output ownership must be auditable. (§1 G8, §4)

### Decision
Sanitize at construction and again at egress; only `term/output.py` accesses stdout/stderr or an output stream. (§3.13, §4, §10.7)

### Alternatives considered
- Direct writes from callers — rejected because they bypass the single egress invariant. (§10.7)

### Consequences
Output has defense in depth and an AST-checkable ownership boundary. (§4, §10.7)

---

## ADR-DD01: No JavaScript

**Status:** [LOCKED]  
**Source:** §12 DD-01

### Context
JavaScript would require an engine, bindings, and an event loop. (§12 DD-01)

### Decision
Drop JavaScript and `script` subtrees. (§12 DD-01)

### Alternatives considered
- Include a JavaScript runtime — rejected as outside bounded text-reader scope. (§12 DD-01)

### Consequences
No page script executes. (§12 DD-01)

## ADR-DD02: No CSS

**Status:** [LOCKED]  
**Source:** §12 DD-02

### Context
A CSS cascade is too large for the bounded semantic text output. (§12 DD-02)

### Decision
Do not implement CSS. (§12 DD-02)

### Alternatives considered
- Implement a visual CSS engine — rejected by scope. (§12 DD-02)

### Consequences
Output is semantic plain text, not visual CSS layout. (§12 DD-02)

## ADR-DD03: No image bytes

**Status:** [LOCKED]  
**Source:** §12 DD-03

### Context
Image decoding and raster output are outside the text reader. (§12 DD-03)

### Decision
Render only `img[alt]` or `[image]`. (§12 DD-03)

### Alternatives considered
- Fetch and rasterize images — rejected by scope. (§12 DD-03)

### Consequences
No image bytes are decoded or rendered. (§12 DD-03)

## ADR-DD04: No HTTP/2

**Status:** [LOCKED]  
**Source:** §12 DD-04

### Context
HTTP/2 framing and connection state exceed the bounded request/response model. (§12 DD-04)

### Decision
Use HTTP/1.1 with `Connection: close`. (§12 DD-04, §9.4)

### Alternatives considered
- Add HTTP/2 — rejected by the locked protocol boundary. (§12 DD-04)

### Consequences
Each response remains independently bounded. (§12 DD-04)

## ADR-DD05: No WebSocket

**Status:** [LOCKED]  
**Source:** §12 DD-05

### Context
Persistent bidirectional channels conflict with the navigation deadline and fixture model. (§12 DD-05)

### Decision
Do not implement WebSockets. (§12 DD-05)

### Alternatives considered
- Add a persistent channel — rejected by scope. (§12 DD-05)

### Consequences
The browser has request/response navigation only. (§12 DD-05)

## ADR-DD06: No `iframe`

**Status:** [LOCKED]  
**Source:** §12 DD-06

### Context
Nested browsing contexts require origin, recursion, and embedding behavior not present here. (§12 DD-06)

### Decision
Do not browse `iframe` contexts. (§12 DD-06)

### Alternatives considered
- Implement nested browsing contexts — rejected by scope. (§12 DD-06)

### Consequences
Nested frame navigation is unsupported. (§12 DD-06)

## ADR-DD07: No authentication or proxy

**Status:** [LOCKED]  
**Source:** §12 DD-07

### Context
Credential storage, challenge flows, and tunnel trust are outside scope. (§12 DD-07)

### Decision
Do not implement authentication flows or proxy support. (§12 DD-07)

### Alternatives considered
- Add credential and proxy management — rejected by scope. (§12 DD-07)

### Consequences
The browser has no authentication or proxy policy. (§12 DD-07)

## ADR-DD08: No Brotli or zstd

**Status:** [LOCKED]  
**Source:** §12 DD-08

### Context
Only stdlib `zlib` gzip/deflate support is permitted. (§12 DD-08)

### Decision
Do not support Brotli or zstd. (§12 DD-08)

### Alternatives considered
- Add another content coding — rejected by the locked runtime boundary. (§12 DD-08)

### Consequences
Content coding support is limited to gzip and deflate. (§12 DD-08)

## ADR-DD09: Hard-cut over-width `pre` content

**Status:** [LOCKED]  
**Source:** §12 DD-09

### Context
Preserving unbounded source lines defeats `MAX_LINE_WIDTH` and render-line memory bounds. (§12 DD-09)

### Decision
Hard-cut over-width `pre` content and expose truncation visibly. (§12 DD-09, §8.7–§8.9)

### Alternatives considered
- Preserve full source lines — rejected because it breaks the width contract. (§12 DD-09)

### Consequences
Over-width preformatted content is real data loss with a visible notice. (§12 DD-09)

## ADR-DD10: Host-only cookies

**Status:** [LOCKED]  
**Source:** §12 DD-10

### Context
Cookie `Domain=` widening can create cross-host leakage. (§12 DD-10)

### Decision
Ignore cookie `Domain=` and keep cookies host-only. (§1 N10, §12 DD-10)

### Alternatives considered
- Honor domain widening — rejected by the security boundary. (§12 DD-10)

### Consequences
Cookies do not widen across hosts. (§12 DD-10)

## ADR-DD11: HTML4 entity table plus `apos`

**Status:** [LOCKED]  
**Source:** §12 DD-11

### Context
A broad practical punctuation table is needed without the full HTML5 table. (§12 DD-11)

### Decision
Use HTML4 named entities plus `apos`; unknown HTML5-only names remain literal. (§12 DD-11)

### Alternatives considered
- Implement the full HTML5 table — rejected because of its size and scope. (§12 DD-11)

### Consequences
The entity set is smaller than HTML5 and explicit. (§12 DD-11)

## ADR-DD12: Provisional node limit

**Status:** [PROPOSED, UNVERIFIED]  
**Source:** §6, §12 DD-12

### Context
`MAX_NODES=25_000` is bounded but lacks attached node counts from real saved article pages. (§12 DD-12)

### Decision
Keep `MAX_NODES=25_000` as a visible, provisional limit pending empirical review. (§6, §12 DD-12)

### Alternatives considered
- Treat the value as evidence-backed — rejected because no empirical corpus exists. (§12 DD-12)

### Consequences
The bound is enforced, but its evidence status remains unverified. (§12 DD-12)

## ADR-DD13: DNS resolution deviation

**Status:** [DEVIATION FROM LOCKED #8] — APPROVED in-session  
**Source:** §9.9, §12 DD-13

### Context
`getaddrinfo` cannot be cancelled, so a timed daemon worker and timed `Thread.join` are used. (§9.9, §12 DD-13)

### Decision
Use the daemon worker for DNS resolution; on timeout fail navigation while the OS-owned resolver call may finish later without owning a socket or issuing a request. (§9.9, §12 DD-13)

### Alternatives considered
- Claim cancellable DNS — rejected because the stdlib call cannot be cancelled. (§9.9)

### Consequences
Navigation timeout is enforced, but the resolver thread has residual lifetime risk; `ARCHITECTURE.md` still records approval as required. (§9.9, §12 DD-13)

## ADR-DD14: Flatten nested tables

**Status:** [LOCKED]  
**Source:** §12 DD-14

### Context
Inner table recovery could corrupt outer rows. (§12 DD-14)

### Decision
Flatten nested table text into the containing cell. (§12 DD-14)

### Alternatives considered
- Render nested table layout — rejected by the bounded tree/layout model. (§12 DD-14)

### Consequences
Nested table layout is not represented. (§12 DD-14)

## ADR-DD15: Never render password values

**Status:** [LOCKED]  
**Source:** §12 DD-15

### Context
Saved-page and REPL output must not disclose password input. (§12 DD-15)

### Decision
Preserve password field type but never render its value. (§8.5, §8.7, §12 DD-15)

### Alternatives considered
- Display password values — rejected by non-disclosure. (§12 DD-15)

### Consequences
Password fields remain visible as fields without their values. (§12 DD-15)

## ADR-DD16: Multiple selects are extracted but not submitted

**Status:** [LOCKED]  
**Source:** §12 DD-16

### Context
The public API accepts one string per field name. (§12 DD-16)

### Decision
Extract multiple-select controls but refuse their submission. (§12 DD-16)

### Alternatives considered
- Change the API to accept multiple values — rejected by the locked public form model. (§12 DD-16)

### Consequences
Multiple-select submission is unavailable. (§12 DD-16)

## ADR-DD17: Unsupported form actions are not fetched

**Status:** [LOCKED]  
**Source:** §12 DD-17

### Context
Non-HTTP(S) form actions are outside the fetch client. (§12 DD-17)

### Decision
Display unsupported forms but refuse submission with `UnsupportedSchemeError`. (§12 DD-17)

### Alternatives considered
- Pass unsupported schemes to HTTP — rejected by URL and fetch rules. (§12 DD-17)

### Consequences
Unsupported actions remain visible but are never fetched. (§12 DD-17)

## ADR-DD18: POST history replay uses GET

**Status:** [LOCKED]  
**Source:** §12 DD-18

### Context
Back/forward must not unintentionally resubmit a POST body. (§12 DD-18)

### Decision
Replay a POST-created history entry as GET without the original body and emit a sanitized notice. (§9.7, §12 DD-18)

### Alternatives considered
- Replay the POST body — rejected by navigation safety. (§12 DD-18)

### Consequences
History remains final-URL-only without automatic form resubmission. (§12 DD-18)

## ADR-DD19: Refuse `Transfer-Encoding` on 304

**Status:** [LOCKED]  
**Source:** §12 DD-19

### Context
A 304 has metadata, not a body, and framing must remain unambiguous. (§12 DD-19)

### Decision
Refuse `Transfer-Encoding` on 304 responses. (§12 DD-19)

### Alternatives considered
- Ignore the header — rejected because it permits ambiguous framing. (§12 DD-19)

### Consequences
The 304 contract is stricter and unambiguous. (§12 DD-19)

## ADR-DD20: No implicit submit control

**Status:** [LOCKED]  
**Source:** §12 DD-20

### Context
An implicit submitter could cause an unexpected POST. (§12 DD-20)

### Decision
Select no submit control by default; require an explicit `name=value` override for a named submitter. (§8.5, §12 DD-20)

### Alternatives considered
- Choose the first submit control automatically — rejected by the deterministic form model. (§12 DD-20)

### Consequences
A submitter is used only when explicitly named. (§12 DD-20)

## ADR-DD21: Disable keep-alive pooling

**Status:** [LOCKED]  
**Source:** §1 N9, §9.1, §12 DD-21

### Context
Connection pooling complicates deadline, framing, and cache interactions. (§12 DD-21)

### Decision
Send `Connection: close` for every response and open a new connection for each hop. (§9.1, §12 DD-21)

### Alternatives considered
- Keep persistent connections — rejected by the bounded HTTP model. (§12 DD-21)

### Consequences
Connection reuse is traded for simpler and more deterministic navigation. (§12 DD-21)

---

## Superseding an entry

When a later decision changes an earlier one, preserve the earlier record and add a new record that explicitly references and supersedes it. (§12, ADR format)
