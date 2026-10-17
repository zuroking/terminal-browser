# Журнал архитектурных решений — `terminal-browser`

Это детальный журнал зафиксированных архитектурных решений. `ARCHITECTURE.md` остаётся источником истины; этот файл фиксирует substance locked decisions #1–#10 и Deliberate Deviations DD-01–DD-21. (§1, §12)

## Формат ADR

Каждая запись указывает status, context, decision, alternatives и consequences. Для каждого архитектурного утверждения указан source section. (§1, §12)

---

## ADR-001: No JavaScript execution

**Статус:** [LOCKED]  
**Источник:** §1 N1, §12 DD-01

### Контекст
Полноценному браузеру потребовались бы JavaScript engine, DOM bindings и event loop. (§12 DD-01)

### Решение
Не выполнять JavaScript; отбрасывать `script` subtrees. (§1 N1, §12 DD-01)

### Рассмотренные альтернативы
- Full JavaScript runtime — отклонён как выходящий за bounded text-reader scope. (§12 DD-01)

### Последствия
Reader остаётся deterministic и bounded, но страницы, зависящие от JavaScript, не становятся интерактивными. (§12 DD-01)

## ADR-002: No CSS engine

**Статус:** [LOCKED]  
**Источник:** §1 N2, §12 DD-02

### Контекст
Cascade и visual layout engine заняли бы основную часть проекта. (§12 DD-02)

### Решение
Не реализовывать CSS selection, cascade, colors или visual layout; выводить semantic plain text. (§1 N2, §12 DD-02)

### Рассмотренные альтернативы
- Browser-compatible CSS engine — отклонён из-за locked scope. (§12 DD-02)

### Последствия
Layout читаем и deterministic, но не является визуальным воспроизведением страницы. (§12 DD-02)

## ADR-003: Text-only image fallback

**Статус:** [LOCKED]  
**Источник:** §1 N3, §12 DD-03

### Контекст
Image fetching, decoding и raster rendering находятся вне text reader. (§1 N3)

### Решение
Использовать только `img[alt]` text или `[image]`, если alternative text отсутствует. (§12 DD-03)

### Рассмотренные альтернативы
- Загрузка и rasterization image bytes — отклонены как выходящие за text-only scope. (§12 DD-03)

### Последствия
Информация об изображении остаётся читаемой без decoding, но visual content недоступен. (§12 DD-03)

## ADR-004: Explicit link and history navigation

**Статус:** [LOCKED]  
**Источник:** §3.15, §9.7, §10.1

### Контекст
Сессии нужна bounded, воспроизводимая navigation model, а не opaque browser history. (§9.7)

### Решение
Поддерживать один bounded history list и position pointer; адресовать links и forms по index. (§1 G4, §3.15, §9.7)

### Рассмотренные альтернативы
- Хранение unbounded page snapshots — отклонено, потому что history является bounded list of committed final URLs. (§9.7)

### Последствия
Back и forward можно тестировать и ограничивать, а старые rendered lines не replay-ятся. (§9.7)

## ADR-005: Bounded deterministic decoding

**Статус:** [LOCKED]  
**Источник:** §3.4, §6, §8.2

### Контекст
Malformed bytes и unknown charset labels не должны ломать navigation. (§3.4, §8.2)

### Решение
Использовать bounded charset allowlist, bounded meta prescan, UTF-8 default и replacement decoding. (§3.4, §8.2)

### Рассмотренные альтернативы
- Raise на каждый unknown label — отклонено, потому что decoding не должен raise из-за charset labels или malformed bytes. (§3.4)

### Последствия
Decoding deterministic и bounded; для malformed input возможны replacement characters. (§3.4, §8.2)

## ADR-006: Persistent HTTP cache with validators

**Статус:** [LOCKED]  
**Источник:** §3.9, §9.5

### Контекст
Повторная navigation должна уметь использовать fresh data и revalidate stale data. (§1 G6, §9.5)

### Решение
Сохранять bounded GET cache entries с freshness metadata и HTTP validators. (§9.5)

### Рассмотренные альтернативы
- Только memory reuse — отклонено, поскольку persistence и validator revalidation являются locked behavior. (§9.5)

### Последствия
GET responses можно переиспользовать и revalidate в пределах byte и freshness limits; POST responses не попадают в cache. (§9.5)

## ADR-007: GET/POST form extraction and submission

**Статус:** [LOCKED]  
**Источник:** §3.14, §8.5, §9.8

### Контекст
Text browser должен показывать basic form controls и выполнять deterministic submission. (§1 G3, §8.5)

### Решение
Извлекать документированные controls и сериализовать формы как GET или POST с bounded encoding. (§3.14, §8.5, §9.8)

### Рассмотренные альтернативы
- Full browser form semantics — отклонено, потому что locked model является документированным subset полей. (§8.5)

### Последствия
Basic forms работают по index, а unsupported и multiple-select случаи остаются явными deviations. (§8.5, §12 DD-16–DD-20)

## ADR-008: TLS-verified, wall-clock-bounded HTTP/1.1

**Статус:** [LOCKED]  
**Источник:** §3.6, §3.10, §6, §9.2, §9.4, §12 DD-13

### Контекст
Сеть должна быть bounded, verifiable и реализуемой standard library. (§1 G1, §2.3 R1, R7–R8)

### Решение
Использовать HTTP/1.1 через stdlib `socket`, `ssl` и `zlib`; проверять TLS certificates и hostnames и применять navigation deadlines. (§3.6, §3.10, §9.2)

### Рассмотренные альтернативы
- High-level HTTP wrappers или HTTP/2 — отклонены locked dependency и protocol rules. (§2.3 R7–R8, §12 DD-04)

### Последствия
Client имеет явные deadlines и verification, а cancellation DNS ограничена approved deviation boundary. (§9.2, §12 DD-13)

## ADR-009: Bounded incremental HTML/DOM pipeline

**Статус:** [LOCKED]  
**Источник:** §3.11–§3.12, §6, §8.3–§8.4

### Контекст
HTML parsing должен останавливать работу до unbounded token, node или depth growth. (§1 G2, G7)

### Решение
Использовать incremental tokenizer и bounded DOM builder с visible truncation. (§3.11–§3.12, §8.3–§8.4)

### Рассмотренные альтернативы
- Строить полный DOM до применения limits — отклонено, потому что limits должны быть incremental. (§6, §8.3)

### Последствия
Большие документы bounded, а truncation visible, но incomplete DOM content может быть omitted. (§6, §8.3–§8.4)

## ADR-010: Sanitized terminal construction and one egress point

**Статус:** [LOCKED]  
**Источник:** §3.13, §4, §10.7

### Контекст
Untrusted text не должен инжектировать terminal controls, а output ownership должен быть auditable. (§1 G8, §4)

### Решение
Очищать при construction и снова при egress; только `term/output.py` обращается к stdout/stderr или output stream. (§3.13, §4, §10.7)

### Рассмотренные альтернативы
- Direct writes из callers — отклонены, поскольку они обходят single egress invariant. (§10.7)

### Последствия
Output имеет defense in depth и AST-checkable ownership boundary. (§4, §10.7)

---

## ADR-DD01: No JavaScript

**Статус:** [LOCKED]  
**Источник:** §12 DD-01

### Контекст
JavaScript потребовал бы engine, bindings и event loop. (§12 DD-01)

### Решение
Отбрасывать JavaScript и `script` subtrees. (§12 DD-01)

### Рассмотренные альтернативы
- JavaScript runtime — отклонён как выходящий за bounded text-reader scope. (§12 DD-01)

### Последствия
Page script не выполняется. (§12 DD-01)

## ADR-DD02: No CSS

**Статус:** [LOCKED]  
**Источник:** §12 DD-02

### Контекст
CSS cascade слишком велик для bounded semantic text output. (§12 DD-02)

### Решение
Не реализовывать CSS. (§12 DD-02)

### Рассмотренные альтернативы
- Visual CSS engine — отклонён по scope. (§12 DD-02)

### Последствия
Output — semantic plain text, а не visual CSS layout. (§12 DD-02)

## ADR-DD03: No image bytes

**Статус:** [LOCKED]  
**Источник:** §12 DD-03

### Контекст
Image decoding и raster output вне text reader. (§12 DD-03)

### Решение
Выводить только `img[alt]` или `[image]`. (§12 DD-03)

### Рассмотренные альтернативы
- Загрузка и rasterization images — отклонены по scope. (§12 DD-03)

### Последствия
Image bytes не декодируются и не рендерятся. (§12 DD-03)

## ADR-DD04: No HTTP/2

**Статус:** [LOCKED]  
**Источник:** §12 DD-04

### Контекст
HTTP/2 framing и connection state выходят за bounded request/response model. (§12 DD-04)

### Решение
Использовать HTTP/1.1 с `Connection: close`. (§12 DD-04, §9.4)

### Рассмотренные альтернативы
- Добавить HTTP/2 — отклонено locked protocol boundary. (§12 DD-04)

### Последствия
Каждый response остаётся independently bounded. (§12 DD-04)

## ADR-DD05: No WebSocket

**Статус:** [LOCKED]  
**Источник:** §12 DD-05

### Контекст
Persistent bidirectional channels конфликтуют с navigation deadline и fixture model. (§12 DD-05)

### Решение
Не реализовывать WebSockets. (§12 DD-05)

### Рассмотренные альтернативы
- Persistent channel — отклонён по scope. (§12 DD-05)

### Последствия
Browser имеет только request/response navigation. (§12 DD-05)

## ADR-DD06: No `iframe`

**Статус:** [LOCKED]  
**Источник:** §12 DD-06

### Контекст
Nested browsing contexts требуют origin, recursion и embedding behavior, которых здесь нет. (§12 DD-06)

### Решение
Не обходить `iframe` contexts. (§12 DD-06)

### Рассмотренные альтернативы
- Nested browsing contexts — отклонены по scope. (§12 DD-06)

### Последствия
Navigation во вложенный frame не поддерживается. (§12 DD-06)

## ADR-DD07: No authentication or proxy

**Статус:** [LOCKED]  
**Источник:** §12 DD-07

### Контекст
Credential storage, challenge flows и tunnel trust вне scope. (§12 DD-07)

### Решение
Не реализовывать authentication flows или proxy support. (§12 DD-07)

### Рассмотренные альтернативы
- Credential и proxy management — отклонены по scope. (§12 DD-07)

### Последствия
Browser не имеет authentication или proxy policy. (§12 DD-07)

## ADR-DD08: No Brotli or zstd

**Статус:** [LOCKED]  
**Источник:** §12 DD-08

### Контекст
Разрешён только stdlib `zlib` gzip/deflate. (§12 DD-08)

### Решение
Не поддерживать Brotli или zstd. (§12 DD-08)

### Рассмотренные альтернативы
- Добавить другой content coding — отклонено locked runtime boundary. (§12 DD-08)

### Последствия
Content coding ограничен gzip и deflate. (§12 DD-08)

## ADR-DD09: Hard-cut over-width `pre` content

**Статус:** [LOCKED]  
**Источник:** §12 DD-09

### Контекст
Сохранение unbounded source lines нарушает `MAX_LINE_WIDTH` и render-line memory bounds. (§12 DD-09)

### Решение
Hard-cut over-width `pre` content и visibly показывать truncation. (§12 DD-09, §8.7–§8.9)

### Рассмотренные альтернативы
- Сохранять полные source lines — отклонено из-за width contract. (§12 DD-09)

### Последствия
Over-width preformatted content — real data loss с visible notice. (§12 DD-09)

## ADR-DD10: Host-only cookies

**Статус:** [LOCKED]  
**Источник:** §12 DD-10

### Контекст
Cookie `Domain=` widening может создать cross-host leakage. (§12 DD-10)

### Решение
Игнорировать cookie `Domain=` и оставлять cookies host-only. (§1 N10, §12 DD-10)

### Рассмотренные альтернативы
- Honoring domain widening — отклонено security boundary. (§12 DD-10)

### Последствия
Cookies не widening между hosts. (§12 DD-10)

## ADR-DD11: HTML4 entity table plus `apos`

**Статус:** [LOCKED]  
**Источник:** §12 DD-11

### Контекст
Нужна практическая punctuation table без full HTML5 table. (§12 DD-11)

### Решение
Использовать HTML4 named entities плюс `apos`; unknown HTML5-only names остаются literal. (§12 DD-11)

### Рассмотренные альтернативы
- Full HTML5 table — отклонена из-за размера и scope. (§12 DD-11)

### Последствия
Entity set меньше HTML5 и остаётся явным. (§12 DD-11)

## ADR-DD12: Provisional node limit

**Статус:** [PROPOSED, UNVERIFIED]  
**Источник:** §6, §12 DD-12

### Контекст
`MAX_NODES=25_000` bounded, но не имеет attached node counts реальных saved article pages. (§12 DD-12)

### Решение
Сохранить `MAX_NODES=25_000` как visible provisional limit до empirical review. (§6, §12 DD-12)

### Рассмотренные альтернативы
- Считать value evidence-backed — отклонено, потому что empirical corpus отсутствует. (§12 DD-12)

### Последствия
Bound применяется, но его evidence status остаётся unverified. (§12 DD-12)

## ADR-DD13: DNS resolution deviation

**Статус:** [DEVIATION FROM LOCKED #8] — APPROVED in-session  
**Источник:** §9.9, §12 DD-13

### Контекст
`getaddrinfo` нельзя отменить, поэтому используется timed daemon worker и timed `Thread.join`. (§9.9, §12 DD-13)

### Решение
Использовать daemon worker для DNS; при timeout navigation завершается ошибкой, пока OS-owned resolver call может позже завершиться без socket или request. (§9.9, §12 DD-13)

### Рассмотренные альтернативы
- Считать DNS cancellable — отклонено, потому что stdlib call нельзя отменить. (§9.9)

### Последствия
Navigation timeout enforced, но resolver thread имеет residual lifetime risk; `ARCHITECTURE.md` всё ещё фиксирует approval as required. (§9.9, §12 DD-13)

## ADR-DD14: Flatten nested tables

**Статус:** [LOCKED]  
**Источник:** §12 DD-14

### Контекст
Inner table recovery мог повредить outer rows. (§12 DD-14)

### Решение
Flatten nested table text в containing cell. (§12 DD-14)

### Рассмотренные альтернативы
- Nested table layout — отклонён bounded tree/layout model. (§12 DD-14)

### Последствия
Nested table layout не represented. (§12 DD-14)

## ADR-DD15: Never render password values

**Статус:** [LOCKED]  
**Источник:** §12 DD-15

### Контекст
Saved-page и REPL output не должны disclose password input. (§12 DD-15)

### Решение
Сохранять password field type, но никогда не render его value. (§8.5, §8.7, §12 DD-15)

### Рассмотренные альтернативы
- Отображать password values — отклонено non-disclosure. (§12 DD-15)

### Последствия
Password fields видны без values. (§12 DD-15)

## ADR-DD16: Multiple selects are extracted but not submitted

**Статус:** [LOCKED]  
**Источник:** §12 DD-16

### Контекст
Public API принимает одну string на field name. (§12 DD-16)

### Решение
Извлекать multiple-select controls, но отказывать в их submission. (§12 DD-16)

### Рассмотренные альтернативы
- Изменить API на multiple values — отклонено locked public form model. (§12 DD-16)

### Последствия
Submission multiple-select недоступен. (§12 DD-16)

## ADR-DD17: Unsupported form actions are not fetched

**Статус:** [LOCKED]  
**Источник:** §12 DD-17

### Контекст
Non-HTTP(S) form actions вне fetch client. (§12 DD-17)

### Решение
Отображать unsupported forms, но refuse submission через `UnsupportedSchemeError`. (§12 DD-17)

### Рассмотренные альтернативы
- Передавать unsupported schemes в HTTP — отклонено URL и fetch rules. (§12 DD-17)

### Последствия
Unsupported actions видимы, но никогда не fetched. (§12 DD-17)

## ADR-DD18: POST history replay uses GET

**Статус:** [LOCKED]  
**Источник:** §12 DD-18

### Контекст
Back/forward не должны непреднамеренно resubmit POST body. (§12 DD-18)

### Решение
Replay POST-created history entry как GET без original body и выдавать sanitized notice. (§9.7, §12 DD-18)

### Рассмотренные альтернативы
- Replay POST body — отклонён navigation safety. (§12 DD-18)

### Последствия
History остаётся final-URL-only без automatic form resubmission. (§12 DD-18)

## ADR-DD19: Refuse `Transfer-Encoding` on 304

**Статус:** [LOCKED]  
**Источник:** §12 DD-19

### Контекст
304 имеет metadata, а не body, и framing должен оставаться unambiguous. (§12 DD-19)

### Решение
Отказывать в `Transfer-Encoding` на 304 responses. (§12 DD-19)

### Рассмотренные альтернативы
- Игнорировать header — отклонено из-за ambiguous framing. (§12 DD-19)

### Последствия
304 contract строже и unambiguous. (§12 DD-19)

## ADR-DD20: No implicit submit control

**Статус:** [LOCKED]  
**Источник:** §12 DD-20

### Контекст
Implicit submitter может вызвать unexpected POST. (§12 DD-20)

### Решение
По умолчанию не выбирать submit control; named submitter требовать explicit `name=value` override. (§8.5, §12 DD-20)

### Рассмотренные альтернативы
- Автоматически выбирать первый submit control — отклонено deterministic form model. (§12 DD-20)

### Последствия
Submitter используется только при явном name. (§12 DD-20)

## ADR-DD21: Disable keep-alive pooling

**Статус:** [LOCKED]  
**Источник:** §1 N9, §9.1, §12 DD-21

### Контекст
Connection pooling усложняет deadline, framing и cache interactions. (§12 DD-21)

### Решение
Отправлять `Connection: close` для каждого response и открывать новое соединение для каждого hop. (§9.1, §12 DD-21)

### Рассмотренные альтернативы
- Persistent connections — отклонены bounded HTTP model. (§12 DD-21)

### Последствия
Connection reuse меняется на более простую и deterministic navigation. (§12 DD-21)

---

## Замена записи

Когда более позднее решение меняет более раннее, сохраняй предыдущую запись и добавляй новую, явно ссылающуюся на неё и заменяющую её. (§12, ADR format)
