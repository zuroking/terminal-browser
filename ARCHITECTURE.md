# ARCHITECTURE.md — `terminal-browser` v2

Source of truth per `CLAUDE.md`. Locked constraints: Python 3.12+, `mypy --strict`,
Pydantic v2, stdlib `ssl`/`socket`/`zlib` for network transport, no
`requests`/`httpx`/`BeautifulSoup`/`html.parser`/`rich` in the render path, one module
at a time in dependency order, and tests that never use the real network.

Legend:

- `[LOCKED]` identifies a design-review decision that may be changed only by
  recording an explicit deviation in §12 and obtaining approval.
- `[PROPOSED]` identifies a bounded implementation default.
- `[DEVIATION ...]` identifies a deliberate departure from a full browser or
  HTTP client. A deviation from a locked decision also says
  `[APPROVAL REQUIRED]` and is not active until approved.

## Traceability: locked decisions #1–#10

| Locked decision | Implementing section(s) |
|---|---|
| #1 — No JavaScript execution | §1, §8.3–§8.4, §12 DD-01 |
| #2 — No CSS engine | §1, §8.7, §12 DD-02 |
| #3 — Text-only image fallback through `alt` | §1, §8.3, §12 DD-03 |
| #4 — Explicit link and history navigation model | §3.15, §9.7, §10.1 |
| #5 — Bounded, deterministic character decoding | §3.4, §6, §8.2, §10.5 |
| #6 — Persistent HTTP cache with validators | §3.9, §9.5, §10.6 |
| #7 — GET/POST form extraction and submission | §3.14, §8.5, §9.8, §12 DD-16–DD-20 |
| #8 — TLS-verified, wall-clock-bounded HTTP/1.1 | §3.6, §3.10, §6, §9.2, §9.4, §10.3, §10.5, §12 DD-13, DD-19; DD-13 blocks implementation until approval |
| #9 — Bounded incremental HTML/DOM pipeline | §3.11–§3.12, §6, §8.3–§8.4 |
| #10 — Sanitized terminal construction and one egress point | §4, §3.13, §10.7 |

---

## 1. Goals and non-goals

### Goals

- G1. Fetch `http://` and `https://` resources over HTTP/1.1 with stdlib
  `socket`, `ssl`, and `zlib`.
- G2. Parse a documented HTML subset with an incremental tokenizer and bounded
  DOM builder.
- G3. Extract and submit basic HTML forms as GET or POST.
- G4. Maintain bounded back/forward history and address links and forms by index.
- G5. Render readable text with deterministic display-width and wrapping rules.
- G6. Persist an HTTP cache and revalidate stale entries with HTTP validators.
- G7. Enforce a named numeric limit on every read, decode, parse, form, render,
  cache, cookie, and history operation.
- G8. Sanitize untrusted text at construction time and again at terminal egress.
- G9. Keep all tests deterministic and hermetic, using local sockets, scripted
  transports, fake clocks, and fixed-seed fuzzing.

### Non-goals

The following v1 decisions remain unchanged:

- N1. JavaScript execution.
- N2. CSS selection, cascade, colors, or visual layout.
- N3. Image fetching, decoding, or raster rendering; only `alt` text is used.
- N4. HTTP/2, ALPN, HPACK, multiplexing, or server push.
- N5. WebSockets or any persistent bidirectional channel.
- N6. `iframe` browsing contexts.
- N7. Authentication flows and proxy support.
- N8. Brotli, zstd, and other content codings beyond `gzip` and `deflate`.
- N9. Keep-alive connection pooling; every request sends `Connection: close`.
- N10. Cookie `Domain=` widening; cookies are host-only.

---

## 2. Module graph and dependency rules

Package root: `src/terminal_browser/`. Each entry is one module file.
`A -> B` means that `A` directly imports `B`.

### 2.1 Modules

- `core/errors.py`
- `core/limits.py`
- `core/clock.py`
- `core/encoding.py`
- `core/sanitize.py`
- `core/text.py`
- `url.py`
- `net/transport.py`
- `net/wire.py`
- `net/cookies.py`
- `net/cache.py`
- `net/http.py`
- `html/entities.py`
- `html/tokenizer.py`
- `html/tree.py`
- `forms.py`
- `render/layout.py`
- `term/output.py`
- `session/session.py`
- `ui/repl.py`
- `cli.py`

### 2.2 Complete direct-import graph

```text
core/clock.py       -> (none)
core/errors.py      -> (none)
core/limits.py      -> (none)
core/encoding.py    -> core/limits.py
core/sanitize.py    -> (none)
core/text.py        -> (none)
url.py              -> core/errors.py
url.py              -> core/limits.py
net/transport.py    -> core/clock.py
net/transport.py    -> core/errors.py
net/transport.py    -> core/limits.py
net/wire.py         -> core/errors.py
net/wire.py         -> core/limits.py
net/cookies.py      -> core/clock.py
net/cookies.py      -> core/errors.py
net/cookies.py      -> core/limits.py
net/cookies.py      -> url.py
net/cache.py        -> core/clock.py
net/cache.py        -> core/errors.py
net/cache.py        -> core/limits.py
net/cache.py        -> net/wire.py
net/http.py         -> core/clock.py
net/http.py         -> core/errors.py
net/http.py         -> core/limits.py
net/http.py         -> url.py
net/http.py         -> net/transport.py
net/http.py         -> net/wire.py
net/http.py         -> net/cookies.py
net/http.py         -> net/cache.py
html/entities.py    -> core/errors.py
html/entities.py    -> core/limits.py
html/tokenizer.py   -> core/errors.py
html/tokenizer.py   -> core/limits.py
html/tokenizer.py   -> html/entities.py
html/tree.py        -> core/errors.py
html/tree.py        -> core/limits.py
html/tree.py        -> core/sanitize.py
html/tree.py        -> html/entities.py
html/tree.py        -> html/tokenizer.py
html/tree.py        -> url.py
forms.py            -> core/errors.py
forms.py            -> core/limits.py
forms.py            -> core/sanitize.py
forms.py            -> html/tree.py
forms.py            -> url.py
render/layout.py    -> core/errors.py
render/layout.py    -> core/limits.py
render/layout.py    -> core/text.py
render/layout.py    -> html/tree.py
term/output.py      -> core/errors.py
term/output.py      -> core/limits.py
term/output.py      -> core/sanitize.py
term/output.py      -> core/text.py
session/session.py  -> core/clock.py
session/session.py  -> core/encoding.py
session/session.py  -> core/errors.py
session/session.py  -> core/limits.py
session/session.py  -> core/sanitize.py
session/session.py  -> url.py
session/session.py  -> net/http.py
session/session.py  -> net/cookies.py
session/session.py  -> net/cache.py
session/session.py  -> html/tree.py
session/session.py  -> forms.py
session/session.py  -> render/layout.py
session/session.py  -> term/output.py
ui/repl.py          -> core/errors.py
ui/repl.py          -> core/sanitize.py
ui/repl.py          -> session/session.py
ui/repl.py          -> term/output.py
cli.py              -> core/errors.py
cli.py              -> core/limits.py
cli.py              -> core/sanitize.py
cli.py              -> session/session.py
cli.py              -> term/output.py
cli.py              -> ui/repl.py
```

No unlisted inter-module import is permitted.

### 2.3 Architectural rules

- R1. The graph is acyclic; `core/*` imports nothing outside `core/*`, and
  `cli.py` is the root.
- R2. `net/*` imports neither `html/*`, `forms.py`, `render/*`, `term/*`, nor
  `session/*`.
- R3. `html/*` imports neither `net/*`, `render/*`, `term/*`, nor `session/*`.
- R4. `render/*` imports neither `net/*`, `term/*`, nor `session/*`.
- R5. `core/encoding.py` and `core/sanitize.py` import no parser, network,
  renderer, or terminal module. This makes them shared leaves rather than
  dependencies of either owner.
- R6. Only `session/session.py`, `ui/repl.py`, and `cli.py` cross fetch, parse,
  form, render, and terminal boundaries.
- R7. Third-party runtime dependencies are limited to Pydantic v2.
- R8. `urllib.parse` is permitted as a parsing primitive. `urllib.request`,
  `http.client`, `email`, `html.parser`, `BeautifulSoup`, `textwrap`, `rich`,
  `requests`, and `httpx` remain prohibited.
- R9. Only `term/output.py` accesses stdout, stderr, or an output stream.
- R10. Public Pydantic boundary models use
  `ConfigDict(frozen=True, strict=True)`. Pydantic header and attribute fields
  use ordered tuples. Token and builder dataclasses may use mutable dict/list
  storage because they are hot-path implementation state and are deep-frozen
  before publication. The review-required `RenderedPage.links: list[Link]` and
  `PageView.links: list[Link]` are the only deliberate list exceptions; session
  creates fresh lists and never mutates them after return.

---

## 3. Public contracts

The code blocks in this section define types and signatures only. They are not
implementation bodies. Recursive public collections use tuples where practical;
header and form order is always preserved.

### 3.1 `core/errors.py`

`ErrorInfo` is immutable and all public exception classes derive from
`BrowserError`.

```python
class ErrorInfo(BaseModel):
    code: str
    module: str
    detail: str
    url: str | None
```

The exception hierarchy is normative in §7.

### 3.2 `core/limits.py`

```python
class Limits(BaseModel):
    connect_timeout_sec: float
    dns_timeout_sec: float
    read_timeout_sec: float
    total_response_timeout_sec: float
    navigation_timeout_sec: float
    max_redirects: int
    max_history: int
    max_body_bytes: int
    max_decompressed_bytes: int
    cache_byte_budget: int
    max_cache_entry_bytes: int
    max_header_size: int
    max_header_count: int
    max_interim_responses: int
    max_dom_depth: int
    max_nodes: int
    max_tokens: int
    chunk_read_size: int
    terminal_width_fallback: int
    min_layout_width: int
    max_render_lines: int
    max_line_width: int
    max_url_len: int
    max_charset_prescan_bytes: int
    max_cookies_per_host: int
    max_cookies_total: int
    max_cookie_store_bytes: int
    max_set_cookie_bytes: int
    max_form_fields: int
    max_form_bytes: int
    max_cookie_header_bytes: int
    max_repl_line_bytes: int
    max_repl_tokens: int
```

```python
class LimitProvider(Protocol):
    def get_limits(self) -> Limits: ...

class LimitsFactory(Protocol):
    def defaults(self) -> Limits: ...
```

The concrete `Limits.defaults()` returns the §6 values. Validation requires
every numeric field to be positive and these cross-field constraints:

```text
dns_timeout_sec <= connect_timeout_sec
read_timeout_sec <= total_response_timeout_sec <= navigation_timeout_sec
max_cache_entry_bytes <= cache_byte_budget
max_body_bytes <= max_cache_entry_bytes < cache_byte_budget
max_set_cookie_bytes <= max_cookie_store_bytes
max_cookies_per_host <= max_cookies_total
min_layout_width >= 4
min_layout_width <= terminal_width_fallback <= max_line_width
max_dom_depth < max_nodes <= max_tokens
max_form_fields <= max_nodes
max_charset_prescan_bytes <= max_body_bytes
max_cookie_header_bytes <= max_cookie_store_bytes
max_repl_line_bytes <= max_form_bytes
max_repl_tokens <= max_form_fields
chunk_read_size <= max_body_bytes
max_render_lines >= 16
```

All constructors that can perform bounded work receive a frozen `Limits` or an
injected `LimitProvider`. They do not read process-global mutable configuration.

### 3.3 `core/clock.py`

```python
class Clock(Protocol):
    def now_monotonic(self) -> float: ...
    def now_epoch(self) -> float: ...
```

`SystemClock` is the production implementation. Tests inject `FakeClock`;
`net/http.py` tests must not use real sleeping to trigger timeout behavior.

### 3.4 `core/encoding.py`

```python
CHARSET_ALLOWLIST: frozenset[str]

def decode_body(
    body: bytes,
    content_type_header: str | None,
    limits: Limits,
) -> str: ...
```

`decode_body` never raises because of a charset label or malformed bytes.
`UnsupportedEncodingError` is not used by this module. The normative algorithm
and prescan are in §8.2.

### 3.5 `core/sanitize.py`

```python
def sanitize_text(text: str) -> str: ...
def sanitize_attribute(value: str) -> str: ...
```

`sanitize_text` and `sanitize_attribute` are the construction-time
sanitizers. `sanitize_text` preserves tabs and newlines. Attribute values are
not layout text: each tab or newline becomes one ASCII space and other
whitespace controls are removed, so an attribute can never inject line
structure or a terminal control.

### 3.6 `core/text.py` and `net/transport.py`

`core/text.py` owns the shared width primitive:

```python
def display_width(text: str) -> int: ...
```

`net/transport.py` owns sockets and TLS:

```python
class TcpTarget(BaseModel):
    host: str
    port: int
    use_tls: bool

class TlsPolicy(BaseModel):
    min_tls_version: ssl.TLSVersion

class TlsContextFactory(Protocol):
    def create(self, policy: TlsPolicy) -> ssl.SSLContext: ...

class ThreadWaiter(Protocol):
    def wait(
        self,
        thread: threading.Thread,
        remaining_sec: float,
    ) -> bool: ...

class Transport(Protocol):
    def resolve(
        self,
        host: str,
        port: int,
        dns_timeout_sec: float,
    ) -> list[socket.AddressInfo]: ...
    def connect(
        self,
        target: TcpTarget,
        remaining_sec: float,
    ) -> socket.socket: ...
    def upgrade_to_tls(
        self,
        sock: socket.socket,
        target: TcpTarget,
        policy: TlsPolicy,
        remaining_sec: float,
    ) -> ssl.SSLSocket: ...
    def send_all(
        self,
        sock: socket.socket,
        data: bytes,
        remaining_sec: float,
    ) -> None: ...
    def recv_bounded(
        self,
        sock: socket.socket,
        max_bytes: int,
        remaining_sec: float,
        chunk_size: int,
    ) -> bytes: ...
    def close(self, sock: socket.socket) -> None: ...
```

Rules:

- `import ssl` is part of this module contract.
- `TlsPolicy` has no `verify` or `check_hostname` field. A non-verifying policy
  is unrepresentable.
- `TcpTarget` has no independently settable `server_hostname`; transport derives
  it from the canonical `host` for every TLS upgrade.
- `check_hostname=True`, hostname verification, and certificate verification
  are unconditional.
- `min_tls_version` is `ssl.TLSVersion`, not a string. Its production default
  and hard permitted floor are `ssl.TLSVersion.TLSv1_2`; any lower value is a
  validation error before a context is created.
- The production context factory uses the system trust store. A test context
  factory is injectable only for fixture CAs; `cli.py` and production call paths
  never obtain or accept a test CA path.
- The default `ThreadWaiter` uses short bounded `Thread.join` slices. Tests
  inject a waiter that advances `FakeClock` and makes the DNS deadline
  deterministic without sleeping.
- `remaining_sec` on every blocking transport call is computed from the
  navigation monotonic deadline and is the minimum of the operation's named
  timeout, the current response deadline, and the whole-navigation budget.
  `resolve` also receives this computed budget. `send_all` checks the clock
  around each bounded send; TLS handshake uses the same remaining budget. A
  nonpositive budget fails before entering the blocking call.
- `close` is idempotent.

### 3.7 `net/wire.py`

This module contains pure byte-to-data functions. It imports no socket, clock,
cache, cookie, or sleep API.

```python
class StatusLine(BaseModel):
    version: Literal["HTTP/1.0", "HTTP/1.1"]
    status: int
    reason: str

HeaderFields = tuple[tuple[str, str], ...]

def parse_status_line(raw: bytes, limits: Limits) -> StatusLine: ...
def parse_headers(raw: bytes, limits: Limits) -> HeaderFields: ...
def decode_chunked(
    chunks: Iterator[bytes],
    limits: Limits,
) -> tuple[bytes, HeaderFields]: ...
```

`decode_chunked` returns the decoded body and trailer fields. The complete
wire contract is in §9.4.

### 3.8 `net/cookies.py`

```python
class Cookie(BaseModel):
    name: str
    value: str
    host: str
    path: str
    secure_only: bool
    http_only: bool
    session_only: bool
    created_at_epoch: float
    expires_at_epoch: float | None

class CookieHeader(BaseModel):
    value: str | None
    notice: str | None

class CookieJar(Protocol):
    def store_from_headers(
        self,
        url: ParsedUrl,
        set_cookie_values: tuple[str, ...],
    ) -> None: ...
    def header_for(self, url: ParsedUrl) -> CookieHeader: ...
    def snapshot(self) -> tuple[Cookie, ...]: ...
    def clear_expired(self) -> int: ...
    def total_bytes(self) -> int: ...
```

The jar receives an injected `Clock`. It returns `CookieHeader.value` for the
request and `CookieHeader.notice` when caps prevent one or more eligible
cookies from being emitted. A `None` value with no notice means there were no
eligible cookies. Rules are normative in §9.6.

### 3.9 `url.py` and `net/cache.py`

```python
class ParsedUrl(BaseModel):
    scheme: Literal["http", "https"]
    host: str
    port: int
    path: str
    raw_query: str
    normalized_url: str

class UrlParser(Protocol):
    def parse(self, reference: str) -> ParsedUrl: ...
    def resolve(self, base: ParsedUrl, reference: str) -> ParsedUrl: ...
    def scheme_of(self, reference: str) -> str: ...
    def normalize_for_cache(self, url: ParsedUrl) -> str: ...
```

`urllib.parse` is the underlying RFC 3986 primitive; URL semantics are not
fully custom. The exact allowed operations and policy are in §9.1.

```python
class CacheKey(BaseModel):
    method: Literal["GET"]
    normalized_url: str

class CacheEntry(BaseModel):
    key: CacheKey
    status: Literal[200]
    headers: HeaderFields
    body: bytes
    stored_at_epoch: float
    fresh_until_epoch: float | None
    etag: str | None
    last_modified: str | None
    body_len: int
    age_at_stored_epoch: float

class Cache(Protocol):
    def get(self, key: CacheKey) -> CacheEntry | None: ...
    def put(self, entry: CacheEntry) -> bool: ...
    def invalidate(self, normalized_url: str) -> int: ...
    def byte_size(self) -> int: ...
    def close(self) -> None: ...
```

A `Cache` is a bounded in-memory LRU backed by an atomic disk persistence
layer. The concrete implementation is never constructed with an unbounded
filesystem budget.

### 3.10 `net/http.py`

```python
class HttpRequest(BaseModel):
    method: Literal["GET", "POST"]
    url: str
    headers: HeaderFields
    body: bytes
    content_type: str | None

class HttpResponse(BaseModel):
    url: str
    status: int
    reason: str
    headers: HeaderFields
    body: bytes
    redirect_chain: tuple[str, ...]
    from_cache: bool
    revalidated: bool
    notices: tuple[str, ...]

class HttpClient(Protocol):
    def request(
        self,
        request: HttpRequest,
        navigation_deadline: float,
    ) -> HttpResponse: ...
```

The client obtains a `CookieHeader` from the jar; a non-null `notice` is
attached to the response/session notice path without becoming a request header.
The client itself does not decide content rendering. It emits default headers,
applies cache/revalidation policy, follows redirects, transfers/decompresses the
body, and returns all final HTTP statuses as normal responses. `HttpRequest`
accepts no caller override for `Host`, `User-Agent`, `Accept`,
`Accept-Encoding`, `Connection`, `Cookie`, `Content-Type`,
`Content-Length`, `Transfer-Encoding`, `If-None-Match`, or
`If-Modified-Since`; those names are reserved and duplicates are rejected with
`ProtocolError` regardless of ASCII case. Other caller header names must be
valid HTTP token names, values must follow §9.4's bounded field grammar, and
duplicate names are rejected case-insensitively. A GET must have an empty body
and a null `content_type`;
POST must have a non-null `content_type` and a body no larger than the form
limit. Conditional cache fields are added internally, not by session callers.

### 3.11 `html/entities.py`

```python
class EntityDecoder(Protocol):
    def decode_text(self, text: str) -> str: ...
    def decode_attribute(self, value: str) -> str: ...
```

Context matters because a legacy reference followed by `=` or an alphanumeric
character is not decoded in an attribute value.

### 3.12 `html/tokenizer.py` and `html/tree.py`

Tokenizer hot-path values are slotted dataclasses, not Pydantic models:

```python
@dataclass(slots=True)
class Token:
    kind: Literal["start", "end", "text", "comment", "doctype", "eof"]
    name: str
    attrs: dict[str, str]
    data: str
    self_closing: bool

class Tokenizer(Protocol):
    def tokenize(self, source: str, limits: Limits) -> Iterator[Token]: ...
```

The builder has a separate mutable slotted node:

```python
@dataclass(slots=True)
class BuilderNode:
    kind: Literal["element", "text"]
    tag: str
    attrs: dict[str, str]
    text: str
    children: list[BuilderNode]
```

Only after parsing completes does the builder deep-freeze its mutable tree into
Pydantic boundary models:

```python
class Node(BaseModel):
    kind: Literal["element", "text"]
    tag: str
    attrs: tuple[tuple[str, str], ...]
    text: str
    children: tuple[Node, ...]

class Document(BaseModel):
    url: str
    title: str
    root: Node
    node_count: int
    truncated: bool
    truncation_reason: Literal["tokens", "nodes", "depth", None]

class TreeBuilder(Protocol):
    def parse(self, url: str, source: str, limits: Limits) -> Document: ...
```

Pydantic validation therefore occurs once at the parse boundary, not for every
token or mutable tree node.

### 3.13 `render/layout.py` and `term/output.py`

```python
class RenderedLine(BaseModel):
    text: str
    kind: Literal[
        "heading", "para", "item", "pre", "rule",
        "table", "blank", "form", "notice"
    ]

class Link(BaseModel):
    href: str
    text: str
    index: int

class RenderedPage(BaseModel):
    url: str
    title: str
    lines: tuple[RenderedLine, ...]
    links: list[Link]
    width: int
    truncated: bool
    truncation_reasons: tuple[Literal[
        "tokens", "nodes", "depth", "render-lines", "pre-width"
    ], ...]

class LayoutEngine(Protocol):
    def render(self, document: Document, width: int) -> RenderedPage: ...
```

```python
class WriteRequest(BaseModel):
    lines: tuple[str, ...]
    width: int
    stream: Literal["stdout", "stderr"]

class WriteResult(BaseModel):
    bytes_written: int
    lines_written: int

class Terminal(Protocol):
    def write(self, request: WriteRequest) -> WriteResult: ...
    def sanitize(self, text: str) -> str: ...
```

`LayoutEngine` does not own `display_width`; callers use `core/text.py` and
layout imports that shared module. Every page `WriteRequest.width` equals the
`RenderedPage.width` effective width. Session notices, REPL prompts, and CLI
diagnostics use the same effective width after `TerminalSize`/fallback
resolution; `Terminal.write` is the final width defense and may hard-cut only
a caller that violated this contract.

### 3.14 `forms.py`

```python
FormFieldType = Literal[
    "text", "password", "hidden", "checkbox",
    "radio", "select", "textarea", "submit"
]

class FormField(BaseModel):
    name: str
    field_type: FormFieldType
    label: str
    value: str
    checked: bool
    required: bool
    disabled: bool
    options: tuple[tuple[str, str], ...]
    selected_options: tuple[str, ...]

class FormSpec(BaseModel):
    index: int
    action: str
    method: Literal["GET", "POST"]
    fields: tuple[FormField, ...]

def extract_forms(
    root: Node,
    document_url: str,
    limits: Limits,
) -> tuple[FormSpec, ...]: ...

def serialize_form(
    form: FormSpec,
    field_values: dict[str, str],
    limits: Limits,
) -> tuple[str, bytes]: ...
```

`serialize_form` returns the resolved navigation URL and the encoded body. For
GET the body bytes are the form query bytes; for POST they are the HTTP request
body. Empty body is `b""`.

### 3.15 `session/session.py`

```python
class PageView(BaseModel):
    url: str
    status: int
    title: str
    lines: tuple[str, ...]
    links: list[Link]
    forms: tuple[FormSpec, ...]
    from_cache: bool
    notices: tuple[str, ...]

class SessionEvent(BaseModel):
    kind: Literal["navigated", "error", "notice"]
    message: str
    url: str | None

class BrowserSession(Protocol):
    def open(self, url: str, width: int) -> PageView: ...
    def follow(self, n: int, width: int) -> PageView: ...
    def back(self, width: int) -> PageView: ...
    def forward(self, width: int) -> PageView: ...
    def submit(
        self,
        form_index: int,
        field_values: dict[str, str],
        width: int,
    ) -> PageView: ...
    def current(self) -> PageView | None: ...
    def history(self) -> tuple[str, ...]: ...
    def close(self) -> None: ...
```

### 3.16 `ui/repl.py` and `cli.py`

```python
class Repl(Protocol):
    def run(self) -> int: ...

class InputLine(BaseModel):
    text: str | None
    over_limit: bool

class BoundedInput(Protocol):
    def read_line(self, max_bytes: int) -> InputLine: ...
```

`InputLine` is a three-state union represented by two validated fields:
`(text=None, over_limit=False)` is EOF; `(text=None, over_limit=True)` is a
discarded over-limit line; `(text=<str>, over_limit=False)` is one normal line.
These states are mutually exclusive.

```python
class TerminalSize(Protocol):
    def width(self) -> int | None: ...

class CliArgs(BaseModel):
    url: str | None
    width: int | None
    cache_dir: str | None
    no_cache: bool
    debug: bool

class Cli(Protocol):
    def run(self, args: CliArgs) -> int: ...
```

---

## 4. Sanitization invariant checkpoints

There are two independent, explicit sanitization checkpoints.

1. Construction checkpoint in `html/tree.py`: every text node and every
   attribute value is passed through `core/sanitize.py` before it is attached
   to the mutable tree and therefore before layout. Form field text and
   extracted values are sanitized when `FormField` values are constructed.
   Session notices, REPL/CLI messages, and any error detail containing a URL
   are sanitized by `core/sanitize.py` before they enter a `PageView` or
   `WriteRequest`.
2. Egress checkpoint in `term/output.py`: `Terminal.write` sanitizes every line,
   enforces `display_width(line) <= request.width`, hard-cuts any over-width
   line to the request width, and then encodes UTF-8. Page layout already
   wraps/hard-cuts normal content; this is a defense-in-depth width boundary
   for prompts, notices, diagnostics, and future callers.

Both checkpoints use the same policy for text; attribute construction uses the
normalization exception described in §3.5:

- Preserve `\n` and `\t` in text.
- Remove C0 controls other than `\n` and `\t`.
- Remove DEL (`U+007F`) and C1 controls (`U+0080`–`U+009F`).
- Remove bidi isolates, embeddings, and overrides (`U+202A`–`U+202E`,
  `U+2066`–`U+2069`).
- Remove the other `Cf` code points used for invisible terminal-confusable
  rendering, including LRM/RLM marks, BOM, and zero-width format controls.
- Remove carriage return; line splitting is performed only on `\n`.
- Never log or write the original unsafe value.

Because the construction sanitizer removes all `Cf`, ZWJ and variation-selector
format controls do not reach layout. Remaining emoji scalars follow the width
policy in §9.1.

Every user-visible string follows this data flow:

```text
wire/form/page text
  -> construction sanitizer
  -> Document/FormSpec/PageView/layout string
  -> Terminal.write line
  -> immediate egress sanitizer
  -> UTF-8 stream
```

This includes notices, exception-derived messages containing a URL, page title,
link labels, form labels, debug tracebacks, and REPL prompts. `ui/repl.py` and
`cli.py` call `core/sanitize.py` before constructing every `WriteRequest`.
A test in `tests/test_egress.py` uses Python `ast` to walk every
`src/**/*.py` file, excludes only `term/output.py`, and fails on calls to
`print`, `sys.stdout.write`, `sys.stderr.write`, their aliases or stream
buffers, `sys.__stdout__`/`sys.__stderr__`, `os.write`, or any imported stream
object. This is the normative egress test.

---

## 5. Core behavioral invariants

- I1. Construction and egress sanitization are both applied; neither is an
  alternative to the other.
- I2. TLS certificate and hostname verification are unconditional and a
  non-verifying policy cannot be represented.
- I3. Every socket read has an explicit byte bound and a per-`recv` timeout.
- I4. The seeded fuzz suite, not an unverifiable catch-all claim, defines parser
  exception behavior; details are in §10.8.
- I5. A navigation is bounded by both per-response and whole-navigation
  wall-clock deadlines.
- I6. Decompression is checked after each inflater output chunk and cannot read
  a declared length into an unbounded allocation.
- I7. Token, node, and DOM-depth limits stop consumption incrementally. Node and
  depth caps produce visible truncation, not exceptions.
- I8. Status and header parsing is bounded by total bytes and field count.
- I9. Memory and disk cache accounting never exceeds `CACHE_BYTE_BUDGET`.
- I10. Cookie scope never widens; expired, oversized, insecure-received, and
  globally capped cookies are handled according to §9.6.
- I11. Character decoding never raises for a missing, unknown, malformed, or
  disallowed charset label; it falls back to UTF-8 with `errors="replace"`.
- I12. Every emitted line satisfies `display_width <= effective width`, including
  `pre` lines, which are hard-cut to that width.
- I13. GET cache keys preserve the raw query byte-for-byte and in order.
- I14. A POST response is never inserted into or looked up from the HTTP cache.
- I15. Repeated response headers, especially multiple `Set-Cookie` fields, are
  preserved as ordered tuples.
- I16. A 4xx or 5xx response is a normal `HttpResponse`; the session keeps its
  status and renders its supported body rather than raising `BadStatusError`.
- I17. Redirects obey the explicit 301/302/303 versus 307/308 method/body
  rules, and a successful history entry contains only the final URL.
- I18. A failed navigation creates no history entry and does not move the
  position pointer.
- I19. `Token`, the builder node, and other tokenizer/tree hot-path values are
  slotted dataclasses; Pydantic validates only the final boundary model.
- I20. Unsupported href schemes are never fetched and receive a visible
  `[unsupported: <scheme>]` suffix.
- I21. DOM/render truncation is represented in the model and visibly surfaced;
  it is never silent.
- I22. The REPL is the default CLI mode; `--url` is a separate one-shot mode.

---

## 6. Resource limits

All limits are frozen fields in `core/limits.py`. Values are `[PROPOSED]`
unless stated otherwise.

| Constant | Default | Enforcement point and rationale |
|---|---:|---|
| `CONNECT_TIMEOUT_SEC` | `5.0` | Per TCP connect attempt. |
| `DNS_TIMEOUT_SEC` | `5.0` | Thread join deadline for `getaddrinfo`; approval pending in DD-13. |
| `READ_TIMEOUT_SEC` | `10.0` | Per `recv`; prevents a blocked call. |
| `TOTAL_RESPONSE_TIMEOUT_SEC` | `30.0` | Headers plus body for one response, independent of per-`recv` timeout. |
| `NAVIGATION_TIMEOUT_SEC` | `60.0` | DNS, cookies, all redirect hops, cache revalidation, and final body for one navigation. |
| `MAX_REDIRECTS` | `5` | Redirect hops after the initial request. |
| `MAX_HISTORY` | `100` | Total history entries across back and forward stacks. |
| `MAX_BODY_BYTES` | `2_000_000` | Bytes received for one response before content decoding. |
| `MAX_DECOMPRESSED_BYTES` | `5_000_000` | Output from one response's inflater. |
| `CACHE_BYTE_BUDGET` | `10_000_000` | Combined accounting cap for persisted cache records. |
| `MAX_CACHE_ENTRY_BYTES` | `2_500_000` | One cache record including body, key, and metadata. |
| `MAX_HEADER_SIZE` | `65_536` | Status line plus all header bytes for one response. |
| `MAX_HEADER_COUNT` | `100` | Header fields for one response. |
| `MAX_INTERIM_RESPONSES` | `5` | Interim 1xx response blocks before one final response. |
| `MAX_DOM_DEPTH` | `64` | Element depth checked before opening each node. |
| `MAX_NODES` | `25_000` | Approved v2 default; truncation is visible. Evidence exception is DD-12. |
| `MAX_TOKENS` | `100_000` | Hard tokenizer backstop independent of node count. |
| `CHUNK_READ_SIZE` | `16_384` | Maximum bytes requested by one `recv`. |
| `TERMINAL_WIDTH_FALLBACK` | `80` | Used when terminal-width detection fails. |
| `MIN_LAYOUT_WIDTH` | `4` | Minimum effective width. |
| `MAX_RENDER_LINES` | `5_000` | Visible rendered output lines. |
| `MAX_LINE_WIDTH` | `120` | Hard requested-width ceiling. |
| `MAX_URL_LEN` | `8_192` | Input URL and redirect target length. |
| `MAX_CHARSET_PRESCAN_BYTES` | `1_024` | First bytes inspected for a meta charset. |
| `MAX_COOKIES_PER_HOST` | `50` | Per-host cookie count. |
| `MAX_COOKIES_TOTAL` | `500` | Global cookie count across all hosts. |
| `MAX_COOKIE_STORE_BYTES` | `65_536` | Global cookie jar serialized-size estimate. |
| `MAX_SET_COOKIE_BYTES` | `8_192` | One raw `Set-Cookie` field before parsing. |
| `MAX_FORM_FIELDS` | `256` | Named fields in one form. |
| `MAX_FORM_BYTES` | `16_384` | Encoded form bytes before request creation. |
| `MAX_COOKIE_HEADER_BYTES` | `8_192` | One outgoing `Cookie` field. |
| `MAX_REPL_LINE_BYTES` | `4_096` | One REPL input line, including command and overrides. |
| `MAX_REPL_TOKENS` | `64` | Whitespace-delimited tokens in one REPL command. |

Additional byte caps that are inherent to existing limits:

- A chunk-size line, including extensions, may not consume more than
  `MAX_HEADER_SIZE`.
- Header and trailer lines use `MAX_HEADER_SIZE` and `MAX_HEADER_COUNT`.
- A single compressed input body may not exceed `MAX_BODY_BYTES`.
- The cache may never contain an entry larger than the total budget, regardless
  of `MAX_CACHE_ENTRY_BYTES`.

No cap is checked only after an entire body, token list, or DOM has been built.

---

## 7. Error taxonomy and ownership

### 7.1 Hierarchy

```text
BrowserError
├── NetworkError
│   ├── DnsError
│   ├── DnsTimeoutError
│   ├── ConnectTimeoutError
│   ├── ReadTimeoutError
│   ├── ResponseTimeoutError
│   ├── NavigationTimeoutError
│   ├── ConnectionLostError
│   └── TlsError
├── ProtocolError
│   ├── HeaderTooLargeError
│   ├── UnsupportedSchemeError
│   ├── TruncatedBodyError
│   └── TokenLimitError
├── HttpError
│   ├── TooManyRedirectsError
│   ├── RedirectError
│   └── BodyTooLargeError
├── DecodeError
│   ├── UnsupportedEncodingError
│   └── DecompressionError
├── ParseError
├── FormError
├── RenderError
├── OutputError
├── InvalidUrlError
└── SessionError
    └── InvalidNavigationError
```

`NodesLimitError` and `DepthLimitError` are removed. Those limits truncate and
set `Document.truncated`; they never raise. `TokenLimitError` is distinct: the
tokenizer backstop raises it, and `TreeBuilder` catches only that error to set
`truncation_reason="tokens"`.

`UnsupportedEncodingError` is only for an unsupported or invalid
`Content-Encoding`. It is never raised for a charset label.

### 7.2 Raised-by contract

| Exception | Raised by | Trigger |
|---|---|---|
| `DnsError`, `DnsTimeoutError` | `net/transport.py` | Resolution failure or resolution join timeout. |
| `ConnectTimeoutError`, `ReadTimeoutError`, `ResponseTimeoutError`, `ConnectionLostError` | `net/transport.py`, `net/http.py` | Connect/read failure, total response deadline, or premature EOF. |
| `NavigationTimeoutError` | `net/http.py` | Whole redirect-chain deadline. |
| `TlsError` | `net/transport.py` | Handshake, trust-chain, or hostname verification failure. |
| `ProtocolError`, `HeaderTooLargeError`, `TruncatedBodyError` | `net/wire.py`, `net/http.py` | Malformed or ambiguous HTTP/1.1 framing. |
| `TokenLimitError` | `html/tokenizer.py` | `MAX_TOKENS` reached. |
| `TooManyRedirectsError`, `RedirectError`, `BodyTooLargeError` | `net/http.py` | Redirect cap/policy, invalid location, or body cap. |
| `UnsupportedEncodingError`, `DecompressionError` | `net/http.py` | Unsupported content coding or invalid/bounded decompression failure. |
| `ParseError` | `html/tree.py` | Internal stack/tree invariant failure, not ordinary malformed HTML. |
| `FormError` | `forms.py` | Invalid method/action, conflicting overrides, or form cap. |
| `UnsupportedSchemeError` from form action | `forms.py` | Submission of a syntactically valid non-HTTP(S) action. |
| `RenderError` | `render/layout.py` | Invalid direct-call width or internal layout invariant failure. |
| `OutputError` | `term/output.py` | Output stream failure or failed sanitized error egress. |
| `UnsupportedSchemeError`, `InvalidUrlError` | `url.py`, `net/http.py` | Unfetchable redirect/request scheme or malformed URL. |
| `SessionError` | `session/session.py` | Empty-history request or committed session invariant failure. |
| `InvalidNavigationError` | `session/session.py` | Invalid link index, unavailable history target, or invalid back/forward transition. |
| `FormError` from submission index | `forms.py` | Invalid form index or impossible field-value request. |

4xx and 5xx statuses do not raise. A 1xx interim response is handled according
to §9.4 and does not become a final error by default.

### 7.3 Catch ownership

- `session/session.py` catches only `BrowserError` subclasses around fetch,
  decode, parse, form, render, and normal output work.
- A caught `BrowserError` becomes a construction-sanitized one-line message in
  `notices` and an error view with the attempted URL, `status=0`, empty `title`,
  `lines=()`, `links=[]`, `forms=()`, and `from_cache=False`. Current page and
  history remain unchanged. If writing that error notice fails, `OutputError`
  propagates.
- Unexpected exceptions are not caught or wrapped by `BrowserSession.open`,
  `follow`, `back`, `forward`, or `submit`; they propagate.
- `cli.py` owns the top-level catch-all. It writes a short sanitized diagnostic
  and returns a non-zero code. It includes a sanitized traceback only when
  `--debug` is present.
- `KeyboardInterrupt` and `SystemExit` retain their normal CLI meaning; they
  are not displayed as page errors.

---

## 8. URL, encoding, HTML, and layout model

### 8.1 URL parsing, resolution, and normalization

`url.py` uses `urllib.parse.urlsplit`, `urlunsplit`, and `urljoin` as the
underlying RFC 3986 subset primitive. It does not use `urllib.request`, fetch,
proxy, or cookie functionality. This is permitted because the project bans
high-level HTTP wrappers, not the stdlib URL parser.

Supported absolute URL schemes are `http` and `https`. The parser:

- lowercases the scheme;
- recognizes bracketed IPv6 literals and canonicalizes them with stdlib
  `ipaddress`;
- converts non-ASCII DNS hosts to IDNA A-labels;
- rejects userinfo, control characters, whitespace, invalid ports, and malformed
  IPv6 brackets;
- stores query as an ASCII string whose characters are the exact percent-encoded
  octets sent on the wire; a Unicode query supplied by a caller is encoded once
  as UTF-8 percent triplets, while an already percent-encoded query is retained
  without escape-case normalization, decoding, or reordering;
- normalizes percent-encoding in the path by decoding percent-encoded
  unreserved ASCII and using uppercase hexadecimal digits for all other
  retained percent triplets;
- percent-encodes Unicode path bytes as UTF-8 without re-decoding reserved
  characters;
- resolves relative references with RFC 3986 merge/replace behavior;
- resolves an `href` against the first valid document `<base href>` when present,
  otherwise against the final document URL; to preserve base semantics without
  materializing tokens, `TreeBuilder` performs one forward, non-tokenizing scan
  of the already-bounded decoded source, checks every complete `base` candidate
  in order, skips malformed or unsupported hrefs, and uses the first valid
  absolute/relative HTTP(S) candidate before consuming the normal incremental
  generator;
- ignores an unsupported or invalid `<base href>` and retains the document URL;
- removes fragments from request targets and normalized representations.

Cache-key normalization is deliberately narrower than general serialization:

1. lowercase scheme and host;
2. remove default port 80 for HTTP or 443 for HTTPS;
3. remove fragment;
4. change an empty path to `/`;
5. preserve `ParsedUrl.raw_query` byte-for-byte, including byte order,
   duplicate parameters, percent-escape spelling, and case. That field is
   validated ASCII and is encoded directly as its UTF-8-equivalent octets.

No query parsing, sorting, or reserialization is permitted in
`normalize_for_cache`. This directly fixes the v1 query-order bug.

`javascript:`, `data:`, and `mailto:` hrefs are never passed to the HTTP
client. During tree construction, their visible anchor text is emitted without a
link marker and with this exact suffix:

```text
[unsupported: javascript]
[unsupported: data]
[unsupported: mailto]
```

If the anchor has no text, the original href text is used before the suffix.
Other non-HTTP schemes are likewise non-links with their lowercased scheme in
the suffix.

### 8.2 Character decoding

`core/encoding.py` owns the entire decode path so `net/*` and `html/*` can use
it without owning it.

Charset allowlist, ASCII case-insensitive:

```text
utf-8
windows-1251
koi8-r
iso-8859-1
windows-1252
```

`decode_body` precedence is:

1. Parse an HTTP `Content-Type` charset parameter. A present HTTP parameter
   always suppresses the meta prescan, even when its value is unknown or
   disallowed.
2. If the HTTP parameter is absent or empty, run a tiny standalone byte-level
   prescan over at most the first `MAX_CHARSET_PRESCAN_BYTES` bytes.
3. Default to UTF-8.

The prescan does not import or call `html/tokenizer.py` or `html/tree.py`. It
case-insensitively locates an ASCII-compatible `<meta` prefix, then a bounded
`charset` token followed by optional whitespace, `=`, optional whitespace, and
an optional quoted ASCII label. The first syntactically valid declaration in
the bounded prefix wins; later conflicting declarations are ignored.

A wire label is used only after lowercasing, trimming, and allowlist matching.
`codecs.lookup` is never called on an unvalidated wire label. Decoding always
uses `errors="replace"`.

A malformed HTTP parameter value is treated as no usable value and allows the
prescan. A syntactically valid but disallowed HTTP or meta label is selected,
fails allowlist matching, and decodes as UTF-8 with replacement. An absent or
unknown meta declaration defaults to UTF-8. No charset path raises.
`decode_body` therefore does not raise `BrowserError` for charset selection or
malformed byte sequences. Content coding errors are separate and are owned by
`net/http.py`.

### 8.3 Supported HTML tags and attributes

Tag names are case-insensitive and stored lowercase.

Supported semantic tags:

```text
a, article, aside, blockquote, base, body, br, button, caption, code, dd, div,
dl, dt, em, b, i, u, strong, footer, form, h1, h2, h3, h4, h5, h6,
head, header, hr, html, img, input, label, li, main, nav, ol, option,
p, pre, section, select, span, table, tbody, td, textarea,
tfoot, th, thead, title, tr, ul
```

`form`, `input`, `select`, `option`, `textarea`, `label`, and `button` are
added for the locked form model.

`img` is a supported void element. It fetches no bytes. Its only layout effect
is inline `alt` text; without `alt`, it emits `[image]`.

Void elements:

```text
br, hr, img, input, meta, link, wbr, base
```

`meta`, `link`, `wbr`, and `base` are recognized as void and dropped. `base` is
consumed by the pre-scan and is not opened in the element stack. `input` is
retained only as a form field and contributes a form-control label to layout.

`script` and `style` remain raw-text elements whose complete subtrees and text
are dropped.

RCDATA elements are `title` and `textarea`: they recognize no nested start tags,
but their character data is entity-decoded. `title` is extracted and omitted
from body flow. `textarea` text is a form default and is rendered as a labeled
control rather than body prose.

Retained attributes:

- `a`: `href`;
- `img`: `alt`;
- `form`: `action`, `method`;
- `input`: `type`, `name`, `value`, `checked`, `disabled`, `required`,
  `placeholder`, `aria-label`;
- `select`: `name`, `disabled`, `required`, `multiple`, `aria-label`;
- `option`: `value`, `selected`, `disabled`;
- `textarea`: `name`, `disabled`, `required`, `placeholder`, `aria-label`;
- `button`: `type`, `name`, `value`, `disabled`, `required`;
- `label`: `for`;
- `base`: `href` for base selection only;
- `meta`: `charset`, `content` for the encoding prescan only.

All other attributes and elements are discarded. Unsupported elements discard
their tag but retain sanitized text children, except `script` and `style`.

Duplicate attributes use the first occurrence. Attribute values are entity
decoded, sanitized, and only then stored.

### 8.4 Tokenization, entities, and tree recovery

The tokenizer yields `Iterator[Token]`; it never constructs a token list. It
emits one EOF token only for input that completes before a hard token cap.
`MAX_TOKENS` raises `TokenLimitError` before token number
`MAX_TOKENS + 1` is yielded. The tree builder catches that specific error,
closes the generator, sets `truncated=True`, and uses reason `tokens`.

Entity handling:

- Numeric decimal and hexadecimal references use `chr()` for valid code points.
- Surrogates, values above `U+10FFFF`, and forbidden control code points become
  `U+FFFD`.
- Named references use the HTML4 named-reference set (approximately 250
  entries), plus `apos` for compatibility with v1. Full HTML5's approximately
  2,000-entry set is not implemented.
- The table includes at least `amp`, `lt`, `gt`, `quot`, `apos`, `nbsp`,
  `mdash`, `ndash`, `hellip`, `laquo`, `raquo`, `rsquo`, `lsquo`, `copy`,
  `reg`, and `trade`.
- Each table entry records whether it permits the legacy no-semicolon form.
- In text context, a permitted legacy form decodes.
- In attribute context, a permitted legacy form does not decode when the next
  character is `=` or ASCII alphanumeric.
- `nbsp` and other non-legacy entries require `;`.
- Unknown references remain literal.
- Entities decode in text nodes, RCDATA, and attribute values. They do not
  decode inside `script` or `style`.

Tree recovery is deterministic:

- A `p` start closes an open `p` as specified by v1.
- A new `li` closes only the nearest open `li` belonging to the same nearest
  list scope. A nested `ul`/`ol` therefore prevents it from closing the outer
  `li` until the nested list scope ends.
- `dt`/`dd`, `tr`, and `td`/`th` implied closes use the same nearest matching
  ancestor rule and never cross a nested scope.
- Nested tables are not supported as independent layout objects. A table start
  encountered while already inside a `table` is dropped as a table element and
  its text descendants are flattened into the containing cell. This prevents
  an inner `td`/`tr` from closing outer table structure.
- An explicit end tag searches from the top of the open-element stack. If a
  matching open element exists, the builder pops unmatched elements above it
  and then pops the match, preserving accumulated children. Thus `<b><i></b>`
  closes both `i` and `b`. If no matching ancestor exists, the end tag is
  ignored.
- Self-closing syntax is honored only for void elements in the supported subset;
  on a non-void element it is treated as a normal start tag.
- Unclosed elements at EOF are closed in stack order and are not truncation.
- A normal comment through `-->` is dropped. A malformed or unterminated
  comment consumes through EOF and is dropped without raising.
- `<!-->` and comments beginning `--!>` are dropped as complete comments.
- In HTML content, `<![CDATA[...]]>` is a bogus comment: consume through the
  next `>` and drop it. It is not treated as foreign HTML content.
- `<?...>` and unsupported `<!...>` constructs are bogus comments: consume
  through the next `>` and drop them.
- A doctype is recognized only by a leading case-insensitive `!doctype` and is
  dropped; malformed doctypes are bogus comments.
- An unterminated start tag at EOF is emitted as sanitized literal text, not as
  an element.
- A NUL in markup becomes `U+FFFD` before sanitization and is then removed only
  if it is a control that the sanitizer policy removes; `U+FFFD` is retained.

Node and depth enforcement happens before adding a `BuilderNode`:

- At `MAX_NODES`, no new node is appended, token consumption stops, the
  generator is closed, and `truncation_reason="nodes"` is set.
- At `MAX_DOM_DEPTH`, an element that would exceed depth is not opened, token
  consumption stops, the generator is closed, and reason `depth` is set.
- Neither path raises `NodesLimitError` or `DepthLimitError`.
- `Document.truncated` is propagated into `RenderedPage.truncated` and rendered
  as a visible notice.

### 8.5 Forms

`forms.py` extracts forms in document order and assigns one-based
`Form.index` values.

Supported field types are exactly:

```text
text, password, hidden, checkbox, radio, select, textarea, submit
```

Input and button type mapping is deterministic:

- missing or `text` input type → `text`;
- `password` → `password`;
- `hidden` → `hidden`;
- `checkbox` → `checkbox`;
- `radio` → `radio`;
- only `input[type=submit]` and `button[type=submit]` map to `submit`;
- `input` reset/image/button types and `button[type=button]` are ignored;
- other input types are ignored.

A form's method is ASCII-uppercased. Missing or `get` selects GET; `post`
selects POST; any other method raises `FormError`. A missing or empty action
uses the current document URL. A nonempty action is resolved against the same
document `<base href>` as links. An unsupported but syntactically valid action
scheme is retained in `FormSpec` and makes the page viewable; only submission
raises `UnsupportedSchemeError`. An invalid action syntax raises `FormError`
during extraction.

A field's label is the first matching label in document order from
`<label for=name>`, then an ancestor `<label>`, then the first non-empty
`aria-label`/`placeholder`, then the field name. `label.text` is sanitized and
entity-decoded.

Successful-control rules:

- unnamed and disabled fields are omitted;
- duplicate enabled names are allowed only for one radio group and repeated
  submit controls; duplicate checkbox names are rejected because one field
  override cannot represent multiple submitted values; at most one radio and
  the first matching submit control can serialize; any other duplicate name
  raises `FormError`;
- checkbox/radio groups require at most one checked member; no checked member
  means the group is omitted;
- checkbox/radio `value` uses the explicit `value` attribute when present and
  otherwise the literal default `on`; unchecked controls are omitted;
- a disabled option is never selected; an option without `value` uses its
  entity-decoded text as the value; `selected` options are retained in
  document order, and a multiple select's selected values remain in
  `selected_options` until submission raises `FormError`;
- checked checkbox/radio fields serialize as `name=value`;
- missing text-like values default to empty string;
- a single select uses its selected option, or the first enabled option when
  none is selected;
- a multiple select extracts successfully but raises `FormError` only if the
  form is submitted, because the public API cannot express repeated values;
- textarea text is RCDATA-decoded and sanitized;
- no submit control is selected by default; if its name appears in
  `field_values`, the first submit control with that exact name is selected;
- disabled submit controls are never selected.

`field_values` must not include unknown names. An absent checkbox/radio key keeps
its extracted default checked state. An explicit false token (`0`, `false`,
`off`, or empty) omits it only when that token is not also the control's
explicit `value`; an explicit control value always wins over false aliases. An
explicit true token (`on`, `1`, `true`, or `yes`) checks it, and any explicit
value equal to the control's own value checks it. A select override must equal
one enabled option's value; an empty option set or unknown value raises
`FormError`. A radio override with the group name checks the one enabled radio
whose value matches the supplied value, and unchecks its peers. If several
enabled radios have the same value, the first in document order is selected.
If all enabled radios use the default value `on`, the literal `on` selects the
first enabled radio deterministically. A nonmatching value raises `FormError`; a false token
with no matching explicit radio value unchecks the entire group. A submit
override must be a nonempty value and selects the first enabled submit control
with that exact name; the selected control serializes its own `value`
attribute, or an empty string when the attribute is absent. Password defaults
are never displayed in the page; layout renders `[password]`.

Serialization:

- Control order is document order.
- Name/value pairs are UTF-8 encoded as
  `application/x-www-form-urlencoded` using `urllib.parse.urlencode`.
- Space becomes `+`; reserved bytes are percent-encoded.
- A GET form appends the encoded pairs as the action's query and has an empty
  HTTP body. The action's prior query is replaced.
- A POST form sets `content_type` to
  `application/x-www-form-urlencoded` and `body` to the encoded bytes; the
  HTTP client emits the required `Content-Length` while constructing the wire
  request;
- `MAX_FORM_FIELDS` and `MAX_FORM_BYTES` are checked before creating a request.
- The resolved action must be syntactically valid. `javascript:`, `data:`,
  `mailto:`, and every other non-HTTP(S) action is retained for display but
  submission refuses it as `UnsupportedSchemeError` and never fetches it.

### 8.6 Display width

`display_width` lives in `core/text.py` and is deterministic across modules.

Policy:

- Combining marks (`Mn`, `Me`) and variation selectors are width 0.
- East-Asian Wide and Fullwidth scalars are width 2.
- Emoji presentation scalars not in those ranges are treated as width 2.
- Ambiguous-width scalars, including most non-Wide CJK punctuation, are width
  1.
- Unassigned and private-use scalars are width 1.
- `Cf` controls have already been removed by the construction sanitizer and are
  not measured.
- Emoji modifiers (skin-tone scalars) attach to the preceding emoji base and
  have width 0; they are never split from that base;
- ZWJ sequences do not reach layout; remaining emoji codepoints are measured
  independently, so a regional-indicator flag occupies 4 cells.
- A combining mark is never split from its base scalar by wrapping.
- `U+00A0` non-breaking space is width 1, never collapsed into ASCII space,
  and is never a wrap point.

All width and emoji tables used at runtime are checked in and generated from one
pinned Unicode version. `unicodedata` may be used only by the offline table
generator and snapshot test, never as a runtime source for width decisions.
The pinned version and all required combining, East-Asian Wide/Fullwidth,
ambiguous, and Emoji_Presentation ranges are explicit data in
`core/text.py`.

### 8.7 Layout flow and wrapping

Block tags are:

```text
p, div, section, article, header, footer, main, nav, aside,
h1-h6, ul, ol, dl, blockquote, pre, table, hr, form
```

Inline tags are:

```text
span, a, em, strong, b, i, u, code, label
```

`br` forces a break. `li`, `dt`, `dd`, and `tr` use the block-like rules below.

General rules:

- A nonempty sanitized `Document.title` is rendered once as a page heading at
  the top, uses the same effective-width wrapping and render-line budget as
  body headings, and is not repeated from an in-body `title` element;
- One blank line separates top-level blocks.
- Headings have one blank line above and below.
- No emitted line has trailing whitespace.
- Outside `pre` and `textarea`, ASCII whitespace collapses to one ordinary
  space. `U+00A0` is exempt and does not create a wrap point.
- Words wrap before the next word that would exceed width.
- Overlong unspaced words hard-break at scalar boundaries while keeping
  combining marks attached.
- CJK text may break between scalars.
- The effective width is `max(MIN_LAYOUT_WIDTH, min(requested_width,
  MAX_LINE_WIDTH))`. The minimum of 4 guarantees progress even for width-2
  scalars.
- Tabs are expanded only here, in layout. Normal text uses 8-column stops; list
  indentation uses 2-column stops. Sanitizers pass tabs through unchanged.

Lists:

- `ul` marker is `- ` with two spaces per level and an eight-level cap.
- `ol` marker is `N. ` and each list starts at 1.
- `dt` is its own line; `dd` is indented four spaces.
- Markers and indentation are laid out before wrap calculation.

Headings:

- `h1` is uppercased before underline generation and width calculation.
- Uppercasing occurs before any width decision because expansion such as
  `ß` → `SS` can change display width.
- `h1` is followed by an `=` underline; `h2`–`h6` use one `#` per level.

`pre`:

- no whitespace collapse and no soft wrap;
- tab stops of 8;
- every source line is hard-cut to effective width, so content past the cut is
  lost;
- trailing blanks are removed;
- hard cuts count as `RenderedPage.truncated=True`.

This real data loss is acknowledged in DD-09.

Tables:

- One logical row is laid out across one or more physical lines. There is no
  silent last-cell ellipsis and no dropped remainder.
- Cells are joined with ` | ` when they fit; a row that exceeds width is wrapped
  in document order across continuation lines.
- The first row containing `th` is a header row and is rendered once, not
  repeated.
- `rowspan`, `colspan`, alignment, captions, and a full CSS-like column solver
  are unsupported.
- Nested tables are not supported; their text is flattened into the containing
  cell as specified in §8.4.

Forms:

- `form` is a block.
- Fields are rendered one per line with their labels and safe control values.
- Passwords render as `[password]`; hidden fields render as a compact hidden
  field marker without their value.
- Submit controls render their label.
- Form indexes are not printed inline. The REPL's `submit <n>` command uses the
  one-based form list carried by `PageView.forms`.

### 8.8 Links

`Link.index` is one-based and follows anchor document order. A fetchable
`http`/`https` anchor produces one `Link` with:

- `href`: resolved absolute URL with fragment removed;
- `text`: sanitized visible anchor text, falling back to the absolute URL;
- `index`: stable one-based number.

Inline rendering inserts a numbered marker immediately after the anchor text:

```text
[1]
[2]
```

The absolute URL is never appended inline and no footnote link list is emitted.
The complete URL exists only in `RenderedPage.links` and `PageView.links`.

An unsupported scheme produces no `Link`, no marker, and the visible suffix
defined in §8.1.

### 8.9 DOM/render truncation visibility

`html/tree.py` truncates, and `render/layout.py` reserves enough final
physical lines for a bounded notice built from `RenderedPage.truncation_reasons`.
The canonical notice is compact and uses these codes:

```text
[truncated: T,N,D,R,P]
```

`T` is token limit, `N` node limit, `D` DOM depth limit, `R` render-line limit,
and `P` preformatted-width loss. Codes appear in that fixed order. Layout
computes the wrapped notice line count, reserves those final lines, and stops
content at the remaining capacity. At the minimum effective width 4 the notice
occupies at most seven lines; `MAX_RENDER_LINES` is therefore validated to be
at least 16. The sanitized notice is wrapped to effective width. Thus a
render-line cap can never hide truncation and a width-4 page never emits an
over-width notice. `RenderedPage.truncated` is exactly
`bool(truncation_reasons)`.

---

## 9. Network, cache, cookies, and navigation semantics

### 9.1 Wire request generation

Every request uses HTTP/1.1 origin-form and these default fields:

```text
Host: <canonical host, bracketed for IPv6, with non-default port>
User-Agent: terminal-browser/2
Accept: text/html, text/plain;q=0.9, */*;q=0.1
Accept-Encoding: gzip, deflate
Connection: close
```

`Cookie` is added from the jar when non-empty. The client computes `Host`; a
caller cannot override it. `If-None-Match` and `If-Modified-Since` are
reserved for internal revalidation and cannot be supplied by a caller. They
are emitted after `Cookie` and before POST content fields in that order.
POST requests add:

```text
Content-Type: application/x-www-form-urlencoded
Content-Length: <decimal byte length>
```

Header order on the wire is deterministic: `Host`, `User-Agent`, `Accept`,
`Accept-Encoding`, `Cookie` when present, `If-None-Match`, `If-Modified-Since`,
then caller-supplied non-reserved headers in their model order, then content
fields for POST. A repeated caller header name is rejected, and a caller
cannot emit any reserved name. `content_type` is null for GET and exactly
`application/x-www-form-urlencoded` for POST; any other value is
`ProtocolError`. The boundary model preserves all response fields in arrival
order.

### 9.2 Redirects and navigation deadlines

Redirect statuses are 301, 302, 303, 307, and 308. A missing, empty, or
malformed `Location` raises `RedirectError`. A syntactically valid location
whose scheme is not HTTP/HTTPS raises `UnsupportedSchemeError`. Relative
locations are resolved against the current request URL.

Method/body policy is explicit:

| Redirect | GET request | POST request |
|---|---|---|
| 301, 302, 303 | remains GET, no body | changes to GET; drop body and form content fields |
| 307, 308 | remains GET, no body | remains POST; preserve method, body, and form content fields |

The body and content type are recalculated for any request before wire encoding.
Cookies and cache eligibility are recomputed for every hop.

A navigation deadline starts before DNS and covers the entire redirect chain,
including conditional cache revalidation and final body transfer. Each response
also receives an independent response deadline covering its headers and body.
Per-`recv` timeout is the minimum of `READ_TIMEOUT_SEC` and remaining navigation
budget. Slow-drip traffic is stopped by the total response and navigation
monotonic deadlines even if each individual `recv` returns before timeout.
The session creates one navigation deadline before DNS, passes it through the
HTTP client and cache/cookie phases, and checks the injected clock before and
after each phase. A phase that begins with no remaining budget raises
`NavigationTimeoutError`; no cache, cookie, decode, or render phase may reset
or extend the navigation deadline.

HTTPS → HTTP redirect is refused. `net/http.py` raises `RedirectError` with a
downgrade-specific code; `BrowserSession` surfaces `[notice] refusing insecure
HTTPS -> HTTP redirect`. The downgrade is never silently followed.

A successful redirect chain pushes only its final URL into history. Intermediate
hops never create history entries.

### 9.3 Response and content dispatch

`net/http.py` does not turn 4xx/5xx into exceptions. They are normal
`HttpResponse` values with their body, and `PageView.status` retains the status.
`session/session.py` owns content dispatch and still lays out a supported
error-page body for 4xx/5xx.

`net/http.py` returns one `Content-Type` field value. The session trims OWS,
lowercases the media type before `;`, and accepts only the exact tokens below.
A missing value is rendered as `<missing>`; a malformed value is rendered as
`<malformed>` and is not parsed.

- `text/html` → call `decode_body`, then HTML tokenizer/tree/layout.
- `text/plain` → call `decode_body`, then render as one `pre` block without HTML
  parsing.
- `204` → empty body and one `no content` notice.
- `304` from cache revalidation → cached body and refreshed metadata; an
  unsolicited/direct 304 is an empty body with a
  `[notice] not modified without cached content` line.
- `205` → empty body and one `reset content` notice.
- any other media type, including missing or malformed `Content-Type` → no
  parsing and one `[notice] unsupported content type: <type>` line.

`Accept-Encoding` supports identity, gzip, and deflate. A single response
coding that is not empty, `identity`, `gzip`, or `deflate` raises
`UnsupportedEncodingError`; comma-separated transfer codings are not accepted.
For `deflate`, zlib first attempts the RFC 1950 zlib-wrapped stream and then a
strict RFC 1951 raw stream. Each `decompress` call uses
`max_length=remaining_decompressed_cap + 1`, rejects output that exceeds the
cap, processes `unconsumed_tail` without an unbounded input buffer, and bounds
`flush()` output. Every output chunk is checked before it is retained.
Failure raises `DecompressionError`.

### 9.4 HTTP/1.1 wire contract

`net/wire.py` is a pure byte boundary:

- status line must be `HTTP/1.0` or `HTTP/1.1`, three decimal digits, and a
  reason phrase no longer than `MAX_HEADER_SIZE`; `parse_status_line` rejects a
  raw line at that bound before parsing;
- field names are non-empty tokens; raw field values accept only HTAB, SP,
  VCHAR (`0x21`–`0x7E`), and obs-text (`0x80`–`0xFF`); CR, LF, NUL, and all
  other controls are rejected before decoding;
- obs-text bytes map one-to-one to U+0080–U+00FF, after which the construction
  sanitizer removes C1 controls before any such value can reach a page string;
  ASCII bytes map to ASCII; field values have a bounded line length;
- field names are lowercased for lookup while the original value is preserved;
- repeated fields are preserved in arrival order, including each `Set-Cookie`;
- `Location`, `Content-Type`, `Content-Encoding`, `ETag`,
  `Last-Modified`, `Age`, `Date`, and `Expires` are singleton fields;
  repeated values for any of them raise `ProtocolError`;
- if neither `Content-Length` nor `Transfer-Encoding` is present, the body is
  close-delimited and is read only to EOF under `MAX_BODY_BYTES` and the
  navigation deadline;
- a `Location` value is resolved relative to the current request URL with the
  RFC 3986 resolver; an empty `Location` is `RedirectError`;
- `Transfer-Encoding` on HTTP/1.0 is rejected as `ProtocolError`;
- obsolete line folding is rejected as `ProtocolError`;
- total status/header bytes and field count are enforced;
- simultaneous `Content-Length` and `Transfer-Encoding` is rejected as
  `ProtocolError`, regardless of field order;
- more than one `Content-Length` field is rejected, even if values are equal;
- `Transfer-Encoding` is accepted only as one field whose complete value is the
  exact token `chunked`; repeated fields, coding lists, transfer extensions, or
  any other coding raise `ProtocolError`;
- a declared `Content-Length` larger than bytes received before EOF raises
  `TruncatedBodyError`;
- bytes received after the declared identity body are not interpreted as another
  response because connections are not reused;
- at most `MAX_INTERIM_RESPONSES` interim response blocks are read; 100, 102,
  and 103 are skipped before reading the next status line; 101 is refused as
  `UnsupportedSchemeError`; statuses 104–199 are unsupported and raise
  `ProtocolError`; every 1xx response must omit `Content-Length` and
  `Transfer-Encoding`, otherwise it is `ProtocolError`;
- 204 and 205 must not contain `Content-Length` or `Transfer-Encoding`;
  either field is malformed framing and raises `ProtocolError`; both have empty
  bodies;
- 304 may carry one `Content-Length` as representation metadata, but it never
  delimits a body; `Transfer-Encoding` on 304 is rejected as `ProtocolError`;
- 4xx/5xx return normally;
- malformed status/header lines raise `ProtocolError`.

Chunked decoding rules:

- each chunk-size line, including hexadecimal digits, `;`, and extensions, is
  capped by `MAX_HEADER_SIZE`;
- extensions are parsed only enough to skip them and are retained nowhere;
- chunk data length is exact and bounded by the remaining response/navigation
  budget;
- premature EOF in declared chunk data, chunk-size digits, or data CRLF raises
  `TruncatedBodyError`; missing framing CRLF after complete data, an oversized
  size line, invalid hex, or extra bytes where a chunk-size line is required
  raises `ProtocolError`;
- the zero chunk must be followed by zero or more bounded trailer fields and a
  final empty line;
- trailers are returned as ordered tuples and are not merged into normal
  response headers;
- a trailer declared `Content-Length` or `Transfer-Encoding` is rejected as
  ambiguous;
- after the terminal chunk, no extra response bytes are consumed on the
  close-delimited socket.

### 9.5 Cache keys, persistence, and freshness

Only successful GET responses participate in cache keys. `CacheKey.method` is
literally `GET`. A POST response is never stored, looked up, revalidated, or
used as a cache key.

The key URL uses §8.1's narrow normalization. In particular, the raw query is
byte-for-byte stable and order remains semantic. Redirect responses are not
cacheable; the final 200 response is stored only under the final response URL,
not under the original navigation URL.

Every network response is processed for `Set-Cookie` before redirect,
cacheability, rendering, or error mapping. This includes 3xx, 4xx, 5xx, and
304. A 304 may therefore update the live cookie jar even though it does not
replace the cached body. Cached headers are never replayed as cookie updates.

The cache is write-through to disk and bounded in memory by the same
`CACHE_BYTE_BUDGET`:

- cache directory is supplied by `CliArgs.cache_dir` or the session
  constructor and is never a module-global; `no_cache` is a session/client
  policy and is not represented as a mutable cache field;
- filenames are derived from SHA-256 of the canonical key and do not contain a
  URL;
- each record has a versioned binary header containing a bounded canonical
  metadata encoding and a body-length prefix, followed by body bytes; the
  metadata format is a checked-in length-prefixed UTF-8 key/value encoding,
  never executable serialization such as pickle, and metadata length/version
  are validated before any value is decoded;
- writes use a temporary sibling file and atomic replace;
- startup reads records defensively, rejects unsupported versions/corruption,
  and evicts invalid records without failing the session;
- LRU metadata is persisted atomically;
- `byte_size` includes body, key, status, and serialized metadata;
- a record larger than `MAX_CACHE_ENTRY_BYTES` or `CACHE_BYTE_BUDGET` is
  rejected;
- eviction is strict LRU until the new record fits;
- cookies from every network response are processed before any other action;
- `Set-Cookie` on a cache hit or 304-served cached metadata is not replayed.
- On a new 200 insertion, `age_at_stored_epoch` is
  `max(0, valid_Age, received_at - valid_Date)`; a missing or invalid `Date`
  makes the apparent-age term zero. A 304 uses the separate merge rule below.

A response is cacheable only if:

- status is 200;
- method is GET;
- no `no-store` directive is present in `Cache-Control`;
- no `Vary` field is present at all, regardless of value;
- the body and total record fit the cache limits;
- no transfer/decompression truncation occurred.

This corrects v1: **any** `Vary`, not only `Vary: *`, makes the response
non-cacheable.

Directive behavior:

- cache-control field names are ASCII case-insensitive and an optional quoted
  string value is accepted/unquoted before comparison;
- `no-store` means never store.
- `no-cache` means the entry may be stored but is stale for every use and must
  be revalidated every time.
- `max-age=N` sets freshness for N seconds.
- `Expires` sets an explicit absolute freshness time when valid.
- When both are valid, `max-age` takes precedence; `Expires` is retained only
  as metadata and is not used for the freshness deadline.
- duplicate `no-store` or `no-cache` directives are harmless; duplicate
  conflicting `max-age` directives make the response non-cacheable.
- `private` does not prevent storage in this single-user cache; it has no
  special effect.

The only implicit freshness is RFC 7234 heuristic Last-Modified freshness.
When no explicit freshness exists and a valid `Last-Modified` is present:

```text
heuristic_lifetime = min(24 hours, (received_at - last_modified) / 10)
```

Invalid or future Last-Modified produces zero heuristic lifetime. HTTP dates
are parsed locally in this order: IMF-fixday, RFC 850 weekday form, and
asctime form, with surrounding OWS and obsolete single-quoted RFC 850 years
accepted. A leap-second value `60` is normalized to the preceding second.
Other/invalid values are absent. Cookie `Expires` accepts those same three
formats plus the cookie-date extension `day-of-month DD-Mon-YYYY HH:MM:SS GMT`
for two-digit years, mapping `70`–`99` to 1970–1999 and `00`–`69` to
2000–2069. If neither explicit freshness nor a valid Last-Modified heuristic
exists, the entry is stored but already stale. There is no invented 60-second
default.

Revalidation:

- Before a hit is considered fresh, compute corrected initial age as
  `max(age_at_stored_epoch, max(0, stored_received_at - effective_stored_Date))`;
  current age is that value plus `max(0, now - stored_received_at)`. A malformed
  `Age` is zero, and a malformed or absent stored `Date` makes the apparent-age
  term zero. This keeps residence time in the calculation even when server
  `Date` is skewed.
  A 304 replaces only metadata fields it supplies: omitted `ETag`,
  `Last-Modified`, `Date`, `Cache-Control`, and `Expires` preserve the stored
  value; a malformed supplied `Date` is ignored and preserves the stored
  `Date`. Let `effective_date` be the valid supplied 304 `Date` when present,
  otherwise the valid stored `Date`; if neither is valid, apparent age is zero.
  Let `prior_age` be
  `age_at_stored_epoch + max(0, receive_time - stored_received_at)`. Let
  `supplied_age` be the valid 304 `Age`, or zero when omitted. The new
  `age_at_stored_epoch` is
  `max(prior_age, supplied_age, max(0, receive_time - effective_date))`, and
  the new stored time is the 304 receive time. A newly supplied `max-age` is
  recalculated from the 304 receive time, while omission of
  `Cache-Control` does not refresh stored `max-age` freshness.
- A fresh hit is returned without network I/O.
- A stale hit causes one conditional network request.
- `ETag` produces `If-None-Match`; `Last-Modified` produces
  `If-Modified-Since`.
- If both exist, both fields are sent.
- A stale entry without a validator performs an unconditional GET.
- 304 serves the cached body and original cache status, refreshes stored time,
  explicit freshness, `ETag`, `Last-Modified`, and cache-control metadata, and
  marks `revalidated=True`; if the 304 carries `no-store` or any `Vary` field,
  invalidate and do not return the entry;
- 200 replaces the stale body and metadata.
- An error response does not overwrite a usable stale entry.
- `--no-cache` bypasses reads, conditional revalidation, and writes for the
  current session.

### 9.6 Cookies

`CookieJar` is host-only and keyed by `(name, canonical_host, path)`. It
receives epoch time from `Clock.now_epoch`; cookie `Max-Age` calculations do
not use monotonic time.

Before parsing any one `Set-Cookie` value, reject the entire field if its UTF-8
byte length exceeds `MAX_SET_COOKIE_BYTES`. Oversized fields are not partially
stored.

Parsing rules:

- split the first `;` into `name=value` and attributes;
- trim OWS around the name and value;
- reject empty/invalid names rather than broadening scope;
- allow cookie values as bounded opaque bytes decoded UTF-8 with replacement;
- cookie-name bytes are restricted to RFC token characters; cookie-value bytes
  exclude controls, whitespace, DQUOTE, comma, semicolon, and backslash;
  malformed values reject the whole field;
- `Max-Age` wins over `Expires`; a non-integer value is ignored;
- `Max-Age <= 0` deletes the matching key;
- an invalid date makes the cookie session-only;
- `HttpOnly` is retained in the model but has no script-related effect;
- `Domain=` is parsed but ignored and never widens host scope;
- `SameSite` is parsed and ignored because there is no script engine.

Storage security:

- A `Secure` cookie received over plain HTTP is rejected, not stored.
- A normal cookie received over either scheme may be stored and sent according
  to scope; send does not retroactively mark it Secure.
- `created_at_epoch` is assigned from `Clock.now_epoch` on new insertion and
  preserved on replacement of the same key.
- Expiry is cleared before every store and send.
- Per-host count is capped at `MAX_COOKIES_PER_HOST`, evicting earliest creation.
- Global count is capped at `MAX_COOKIES_TOTAL`, evicting globally earliest
  creation and then the lowest internal use sequence.
- Global estimated storage is capped at `MAX_COOKIE_STORE_BYTES` with the same
  deterministic oldest-first eviction.
- The jar keeps a private monotonically increasing use sequence for every
  successful send. Equal epoch creation values are ordered by that sequence,
  then by name; no public cookie field or wall-clock value is needed for
  deterministic eviction.

Path matching:

- default path is the request directory path, or `/` when absent;
- explicit `Path` must begin with `/`; otherwise the default path is used;
- request `/foo` does not match cookie path `/foobar`;
- a cookie path matches when equal, is a prefix ending at `/`, or the request
  path starts with the cookie path followed by `/`.

Send order is longest path first, then earliest creation, then name. Secure
cookies are sent only for HTTPS. The jar returns one deterministic
`Cookie: n=v; n2=v2` field. A header that would exceed
`MAX_COOKIE_HEADER_BYTES` is not partially emitted; eligible cookies are
selected in order until the next complete pair would exceed the named limit,
and an error notice is generated if no pair fits.

### 9.7 Link-follow navigation and history

History is one bounded list plus a zero-based position pointer. The list holds
committed final URLs only; it does not hold unbounded `PageView` objects.

A successful `open`, `follow`, or form `submit`:

1. obtains the final URL after redirects;
2. completes decode, parse, form extraction, layout, and terminal output;
3. only then commits current page and history.

Failure behavior:

- a failed navigation creates no history entry;
- a failed navigation does not move the position pointer;
- a failed navigation does not change current page;
- cookies/cache side effects that occurred before the failure are retained;
  navigation history is not a rollback mechanism for network side effects.

Forward-history behavior:

- on a successful new `open()` or `follow()` from a non-tip position, all
  entries after the current position are truncated before the new final URL
  is appended;
- this truncation occurs only on successful commit, so a failed attempted
  navigation preserves forward history;
- redirect hops do not each truncate or append history;
- repeated URLs are not deduplicated;
- when a successful commit would exceed `MAX_HISTORY`, the oldest entry is
  removed first. Because a commit truncates forward history and makes the new
  entry the tip, this preserves the new current entry and every retained
  back entry.

`back(width)` and `forward(width)` perform a fresh GET/cache/revalidation
render of the target URL at the requested width. They do not replay old lines.
An entry created by a POST form is replayed as GET with no body and a sanitized
notice, never as an automatic form resubmission. If the target redirects, the
committed history entry is replaced with the new
final URL, the pointer is moved to that entry, and entries after it remain
unchanged. On success the pointer is at the committed final URL. On failure
the pointer and target entry remain unchanged. Calling at a boundary or
following an invalid link index raises `InvalidNavigationError`, a
`SessionError` subclass; the REPL converts that `BrowserError` to a notice.

`follow(n)` resolves exactly one link from the current `PageView.links`; an
out-of-range or nonpositive `n` raises `InvalidNavigationError`, then performs
the same commit semantics as `open`.

### 9.8 Form submission navigation

`submit(form_index, field_values, width)`:

1. selects the form from current `PageView.forms`; an out-of-range index or
   invalid current page raises `FormError`;
2. validates and serializes the named fields;
3. resolves GET query or creates the POST request body;
4. starts a new navigation with a new whole-navigation deadline;
5. applies the redirect method rules in §9.2;
6. commits only the final URL after a successful full page render/write.

A form submission is not a history traversal and therefore truncates forward
history on successful commit, like `open` and `follow`.

### 9.9 DNS timeout decision requiring approval

`socket.getaddrinfo` has no cancellation or timeout parameter. The proposed
implementation is:

- run one resolution call on a named daemon worker thread;
- wait through an injected `ThreadWaiter`; the production waiter joins in short
  slices until the `Clock.now_monotonic` deadline, while a test waiter advances
  `FakeClock` deterministically;
- on timeout, close the transport state, raise `DnsTimeoutError`, and discard
  any later worker result;
- a timed-out OS resolver call may continue until the OS returns because Python
  cannot safely kill it;
- the worker owns no socket and cannot perform a request, so its only residual
  effect is a short-lived resolver thread.

This is an unavoidable deviation from an ideal total-time guarantee and is
recorded as DD-13 with `[DEVIATION FROM LOCKED #8] [APPROVAL REQUIRED]`.

---

## 10. REPL, CLI, and test contracts

### 10.1 REPL

`cli.py` starts `ui/repl.py` by default. It is line-based and accepts:

```text
open <url>
follow <n>
back
forward
submit <n> [name=value ...]
quit
```

The injected `BoundedInput` returns an `InputLine`: `(text=None, over_limit=False)` is EOF,
`(text=None, over_limit=True)` is a discarded overlong line, and
`(text=<str>, over_limit=False)` is one normal line. It decodes input as UTF-8 with `errors="replace"` and then applies
`sanitize_text`; invalid bytes never escape the reader. `TerminalSize.width()`
is optional: an unavailable or invalid result uses `TERMINAL_WIDTH_FALLBACK`,
then layout applies `MIN_LAYOUT_WIDTH`. The input reader accepts at most
`MAX_REPL_LINE_BYTES` bytes and at most `MAX_REPL_TOKENS` whitespace-delimited
tokens per line. It reads at most the named byte cap into a bounded buffer; if
a line exceeds either cap it discards through the next newline and emits a
sanitized notice without parsing. No unbounded `readline()` or split operation
is used. `submit <n>` with no
overrides uses form defaults and any checked successful controls. An override
token is split only on the first `=`; its name must exist on the form. Blank
lines are ignored. Unknown commands produce a sanitized notice and do not exit.
`quit` returns 0.

Prompt, normal page lines, and informational command feedback are
`WriteRequest(stream="stdout")` values through `Terminal`; handled errors and
debug diagnostics use `stream="stderr"`. The REPL never calls an output stream
directly. EOF returns 0 after closing the session through `BrowserSession.close`.
`KeyboardInterrupt` exits with 130.

### 10.2 CLI modes and exit codes

- No `--url`: interactive REPL, the default.
- `--url URL`: one-shot navigation and exit; no REPL prompt is printed.
- `--width N`: explicit width.
- `--no-cache`: bypass cache reads, revalidation, and writes.
- `--debug`: top-level unexpected exceptions include a sanitized traceback.

Exit codes:

- `0`: normal exit, successful one-shot navigation, or `quit`;
- `1`: handled navigation failure in one-shot mode or CLI top-level unexpected
  exception;
- `2`: argument parsing/validation failure;
- `130`: `KeyboardInterrupt`.

`BrowserSession` catches `BrowserError` and writes a notice. Any unexpected
exception escaping a session method is caught only by `cli.py`; it becomes a
short sanitized message, with traceback only under `--debug`.

### 10.3 Local fixture server and certificates

No test contacts the real network. `tests/fixture_server.py` binds
`127.0.0.1:0` for integration tests. It provides at least:

1. `ok` — 200 HTML with `Content-Length`.
2. `chunked` — multiple chunks, extensions, and trailers.
3. `truncated` — declared length larger than bytes sent.
4. `malformed-headers` — bad status, NUL, missing colon, obs-fold.
5. `ambiguous-framing` — Content-Length plus Transfer-Encoding and duplicate
   Content-Length.
6. `oversize-headers`, `oversize-chunk-line`, and `big-body`.
7. `bad-charset` and conflicting `meta charset`.
8. `gzip`, `deflate`, and `gzip-bomb`.
9. redirect chains including 301/302/303/307/308 for GET and POST, downgrade,
   relative locations, unsupported schemes, and loops.
10. duplicate headers and multiple `Set-Cookie` fields.
11. cache `max-age`, `Expires`, `no-cache`, `no-store`, any `Vary`, ETag,
    Last-Modified, 304, and changed 200.
12. cookie Secure-over-HTTP, Max-Age, Expires, bad dates, deletion, and global
    eviction.
13. text/html, text/plain, unsupported content type, 1xx, 204, 304, 404, and
    500.
14. `good-cert` — fixture CA, matching SAN, and currently valid certificate;
    the integration test requires a successful verified handshake.
15. `bad-cert` — untrusted/self-signed chain.
16. `hostname-mismatch` — otherwise valid fixture CA, currently valid
    certificate, but certificate SAN does not match the connected host.
17. `expired-cert` — otherwise valid fixture CA and matching hostname, but the
    certificate `notAfter` is in the past.

The checked-in certificate generation command, SAN names, subject, issuer,
fingerprints, creation date, expiry date, and regeneration procedure must be
documented in `tests/certs/README.md` or a test-module docstring when those
files are implemented, not in this architecture. Certificates require periodic
regeneration before expiry.

### 10.4 Scripted transport and fake clock

The sleep-based v1 `slow` socket test is removed. `net/http.py` tests use:

- `ScriptedTransport`, a fake implementing `Transport`;
- scripted byte sequences for each response/hop;
- `FakeClock` advancing only when scripted progress says it should;
- assertions on `READ_TIMEOUT_SEC`, `TOTAL_RESPONSE_TIMEOUT_SEC`, and
  `NAVIGATION_TIMEOUT_SEC`.

A slow-drip script returns one byte at a time while `FakeClock` advances less
than the per-read timeout each time; the total response deadline must still
stop it. The script contains no real `time.sleep`.

Real local sockets remain required for transport integration and TLS handshake
verification.

### 10.5 Pure `net/wire.py` tests

`net/wire.py` has unit tests with no socket fixture. They cover status lines,
header multimap preservation, all framing conflicts in §9.4, chunk-size caps,
extensions, trailers, truncation, and malformed byte inputs.

Encoding, transport, and form tests explicitly cover:

- allowed charset precedence and fallback;
- meta prescan within exactly 1,024 bytes;
- unvalidated labels never reaching `codecs.lookup`;
- TLS certificate trust failure, hostname mismatch, and expired certificate;
- scripted total response and whole-navigation deadlines;
- GET and POST forms and byte-identical serialization;
- all redirect method/body combinations;
- HTTPS→HTTP downgrade refusal;
- POST never touching the cache.

### 10.6 Persistence and cache tests

Cache tests cover disk restart, atomic-write recovery from an invalid record,
byte-budget accounting, LRU eviction, GET-only keys, byte-for-byte query order,
any `Vary`, `no-store`, always-stale `no-cache`, explicit freshness, the exact
Last-Modified heuristic, no implicit 60-second freshness, ETag 304,
Last-Modified 304, both validators, 200 replacement, and failure without stale
overwrite.

### 10.7 Terminal egress test

`tests/test_egress.py` uses `ast`, not a text grep, and scans all production
`.py` files under `src/`. It excludes only `term/output.py` and fails on:

- calls whose resolved function name is `print`;
- calls to `sys.stdout`, `sys.stderr`, `sys.__stdout__`, or `sys.__stderr__`
  or their `.write`/`.buffer.write` chains;
- calls to an import alias of either standard stream;
- calls to `os.write` using a standard output descriptor;
- any other stream/file object imported or opened for writing outside
  `term/output.py`.

Additional terminal-byte tests feed adversarial titles, URLs, notices, link
text, form labels, and traceback text and assert no escape, C0/C1, DEL, bidi, or
other stripped `Cf` byte sequence reaches the test stream.

### 10.8 Seeded fuzz suite

`tests/test_fuzz.py` uses stdlib `random.Random` with a checked-in fixed seed
and a deterministic corpus generator. It feeds malformed and random inputs to:

- `html/tokenizer.py`;
- `html/tree.py`;
- `render/layout.py`;
- `term/output.py`.

For each call, the test asserts that execution either returns normally or
raises only a `BrowserError` subclass. It never treats a standard-library or
arbitrary exception as acceptable. `MemoryError` and `KeyboardInterrupt` are
not generated by this fuzz corpus. The suite has a fixed iteration count and
runs in ordinary `pytest -v` without real network access.

This concrete seeded test replaces v1's unverifiable statement that “no other
exception escapes.”

### 10.9 Per-module matrix

| Module | Required tests |
|---|---|
| `core/errors.py` | Full hierarchy and `ErrorInfo` frozen/strict validation. |
| `core/limits.py` | Default snapshot, positivity, cross-cap invariants. |
| `core/clock.py` | System monotonic/epoch ordering; fake monotonic non-decreasing. |
| `core/encoding.py` | HTTP/meta/default precedence, allowlist, invalid labels, replacement decoding, no token parser dependency. |
| `core/sanitize.py` | C0/C1/DEL/bidi/Cf, tab/newline preservation, URL-containing detail. |
| `core/text.py` | CJK, emoji, ambiguous width, combining marks, NBSP. |
| `url.py` | Relative resolution, base, IPv6, IDNA, percent normalization, query-byte identity, unsupported schemes. |
| `net/transport.py` | Connect/refusal, bound reads, good-cert verified handshake, untrusted chain, hostname mismatch, expired cert, idempotent close. |
| `net/wire.py` | All pure byte/framing/chunk/trailer contracts; no socket fixture. |
| `net/cookies.py` | Caps, creation order, Secure rejection, path boundary, expiry, global eviction. |
| `net/cache.py` | Persistence, revalidation metadata, all cache directives, any Vary, GET-only. |
| `net/http.py` | Scripted transport, fake clock, headers, statuses, redirects, body, coding, cache. |
| `html/entities.py` | HTML4 table, legacy no-semicolon text/attribute distinction, numeric replacement. |
| `html/tokenizer.py` | Generator laziness, all lexical modes, RCDATA/raw text, comments/CDATA, caps. |
| `html/tree.py` | Scoped implied ends, mismatched closes, incremental caps, freeze once, links/base/sanitization. |
| `forms.py` | Every field type, labels, successful controls, encoding, limits, unsupported action. |
| `render/layout.py` | Width, wrapping, NBSP, emoji, headings-before-width, pre cut, multiline tables, links, notices. |
| `term/output.py` | Construction/egress defense in depth and actual clean bytes. |
| `session/session.py` | BrowserError mapping, unexpected propagation, history atomicity, forms, final redirect URL. |
| `ui/repl.py` | Commands, default interactive loop, one-shot isolation, prompt sanitization. |
| `cli.py` | Mode selection, exit codes, top-level catch-all, debug traceback. |

---

## 11. Build order

Implement one module at a time in this order, stopping after each module. After
each module, run `pytest -v` and `mypy --strict` and print the raw terminal
output without summarizing it.

1. `core/errors.py` — sole exception root.
2. `core/limits.py` — named constants and frozen `Limits`.
3. `core/clock.py` — monotonic/epoch seam.
4. `core/encoding.py` — charset and decode policy.
5. `core/sanitize.py` — construction/egress sanitization primitive.
6. `core/text.py` — shared display width.
7. `url.py` — parsing, resolution, IDNA/IPv6, cache normalization.
8. `net/transport.py` — **blocked until DD-13 DNS behavior is explicitly
   approved**; then implement sockets, TLS, and DNS/connect/read seams.
9. `net/wire.py` — pure HTTP framing and chunk decoder.
10. `net/cookies.py` — clock-backed bounded jar.
11. `net/cache.py` — memory LRU plus disk persistence and validators.
12. `net/http.py` — request orchestration, deadlines, redirects, cache.
13. `html/entities.py` — HTML4 table and context rules.
14. `html/tokenizer.py` — incremental generator.
15. `html/tree.py` — mutable builder, links/base, freeze, truncation.
16. `forms.py` — extraction and deterministic serialization.
17. `render/layout.py` — shared-width layout, tables, forms, links, notices.
18. `term/output.py` — only stdout/stderr owner and second sanitizer pass.
19. `session/session.py` — navigation, forms, history, error mapping.
20. `ui/repl.py` — line-based interactive default.
21. `cli.py` — one-shot mode, flags, top-level catch-all.

No module may be implemented before all listed dependencies, and no behavior
outside this document may be added without updating this architecture first.

---

## 12. Deliberate Deviations

Each item records a departure from a complete browser, HTTP client, or a locked
review decision. A locked override is not active until explicitly approved.

- DD-01. No JavaScript. A JS engine, DOM bindings, and event loop are outside a
  bounded text reader; `script` subtrees are dropped (§8.3–§8.4).
- DD-02. No CSS. A cascade and visual layout engine dominate scope; output is
  semantic plain text (§8.7).
- DD-03. No image bytes. Only `img[alt]` or `[image]` appears (§8.3).
- DD-04. No HTTP/2. Framing, HPACK, multiplexing, and connection-state behavior
  are excluded; HTTP/1.1 with `Connection: close` keeps each response bounded
  (§9.4).
- DD-05. No WebSocket. Bidirectional persistent channels conflict with the
  request/response, navigation-deadline, and fixture model (§1 N5).
- DD-06. No `iframe`. Nested browsing contexts require origin, recursion, and
  layout-embedding behavior not present here (§1 N6).
- DD-07. No authentication or proxy. Credential storage, challenge flows, and
  tunnel trust are excluded (§1 N7).
- DD-08. No Brotli/zstd. Only stdlib `zlib` gzip/deflate is supported (§9.3).
- DD-09. `pre` content beyond the effective width is hard-cut and lost. Rationale:
  preserving unbounded source lines defeats `MAX_LINE_WIDTH` and the render-line
  memory contract. This is real data loss and is explicitly visible through
  `RenderedPage.truncated` plus a truncation notice (§8.7, §8.9).
- DD-10. Cookie `Domain=` is ignored. Cookies remain host-only, eliminating
  cross-host leakage by construction (§9.6).
- DD-11. The named-entity set is HTML4 plus `apos`, not full HTML5. Rationale:
  common punctuation and Cyrillic-adjacent text need broad practical coverage
  without roughly 2,000 table entries; unknown HTML5-only names remain literal
  (§8.4).
- DD-12. `[PROPOSED, UNVERIFIED]` `MAX_NODES=25_000` is selected without
  attached node counts from two or three real saved article pages. No empirical
  page corpus exists at this stage of the project (architecture precedes parser
  implementation). 25,000 is a provisional value, not evidence-backed. It must
  be revisited with real node counts from saved article pages once `html/tree.py`
  exists and before this limit is treated as final. The value still enforces a
  bound and every truncation is visible (§6, §8.9).
- DD-13. `[DEVIATION FROM LOCKED #8] [APPROVAL REQUIRED]` DNS resolution uses a
  daemon worker plus timed `Thread.join` because stdlib `getaddrinfo` cannot be
  cancelled. On timeout the navigation fails, but the resolver thread may live
  until the OS call returns; it owns no socket and cannot issue a request
  (§9.9). Approval is required before implementation of `net/transport.py`.
- DD-14. Nested tables are unsupported as table layout. Their text is flattened
  into the containing cell so inner table implied-end rules cannot corrupt
  outer rows (§8.4, §8.7).
- DD-15. Password field values are never rendered. This preserves the form
  field type while preventing saved-page or REPL output from disclosing input
  (§8.5, §8.7).
- DD-16. Multiple-select controls are extracted but cannot be submitted because
  the required public API accepts one `str` per field name. Single-select,
  checkbox, radio, textarea, hidden, text, password, and submit controls remain
  supported (§8.5).
- DD-17. Non-HTTP(S) form actions are displayed as forms but are never fetched;
  submission refuses them as `UnsupportedSchemeError` (§8.5, §9.8).
- DD-18. History replay of an entry created by POST uses GET, never replays the
  original body, and emits a sanitized notice. This prevents back/forward from
  becoming an unintended form resubmission while preserving the final-URL-only
  history model (§9.7).
- DD-19. `Transfer-Encoding` is refused on 304 even though a permissive HTTP
  parser could ignore it. This keeps body framing unambiguous and treats 304
  metadata as non-body data (§9.4).
- DD-20. No submit control is selected by default. This avoids an implicit,
  potentially surprising POST and requires an explicit `name=value` override
  for a named submitter (§8.5).
- DD-21. Keep-alive/connection pooling is disabled. Every response uses
  `Connection: close`; this keeps deadline, framing, and cache interactions
  simple at the cost of a new connection for every hop (§1 N9, §9.1).
