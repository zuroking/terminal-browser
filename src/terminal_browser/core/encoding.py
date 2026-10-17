from .limits import Limits


CHARSET_ALLOWLIST: frozenset[str] = frozenset(
    {
        "utf-8",
        "windows-1251",
        "koi8-r",
        "iso-8859-1",
        "windows-1252",
    }
)


def _normalize_label(value: str) -> str:
    return value.strip().strip("\"'").strip().lower()


def _http_charset(content_type_header: str | None) -> str | None:
    if content_type_header is None:
        return None
    for parameter in content_type_header.split(";")[1:]:
        name, separator, value = parameter.partition("=")
        if not separator or name.strip().lower() != "charset":
            continue
        label = _normalize_label(value)
        if label in CHARSET_ALLOWLIST:
            return label
    return None


def _ascii_label(value: bytes) -> str:
    return value.decode("ascii", errors="ignore").strip().lower()


def _meta_attributes(tag: bytes) -> dict[bytes, bytes]:
    attributes: dict[bytes, bytes] = {}
    index = 0
    while index < len(tag):
        while index < len(tag) and tag[index] in b" \t\r\n\f/":
            index += 1
        name_start = index
        while index < len(tag) and tag[index] not in b" \t\r\n\f/=>":
            index += 1
        if name_start == index:
            index += 1
            continue
        name = tag[name_start:index].lower()
        while index < len(tag) and tag[index] in b" \t\r\n\f":
            index += 1
        if index >= len(tag) or tag[index] != ord("="):
            continue
        index += 1
        while index < len(tag) and tag[index] in b" \t\r\n\f":
            index += 1
        if index < len(tag) and tag[index] in (ord("\""), ord("'")):
            quote = tag[index]
            index += 1
            value_start = index
            while index < len(tag) and tag[index] != quote:
                index += 1
            value = tag[value_start:index]
            if index < len(tag):
                index += 1
        else:
            value_start = index
            while index < len(tag) and tag[index] not in b" \t\r\n\f>":
                index += 1
            value = tag[value_start:index]
        if name in {b"charset", b"content", b"http-equiv"}:
            attributes.setdefault(name, value)
    return attributes


def _content_charset(content: bytes) -> str | None:
    for parameter in content.split(b";"):
        name, separator, value = parameter.partition(b"=")
        if not separator or _ascii_label(name) != "charset":
            continue
        return _ascii_label(value.strip().strip(b"\"'"))
    return None


def _prescan_charset(body: bytes, window_size: int) -> str | None:
    prefix = body[:window_size].lower()
    search_start = 0
    while True:
        tag_start = prefix.find(b"<meta", search_start)
        if tag_start < 0:
            return None
        name_end = tag_start + len(b"<meta")
        if name_end >= len(prefix) or prefix[name_end] not in b" \t\r\n\f/>":
            search_start = name_end
            continue
        tag_end = prefix.find(b">", name_end)
        if tag_end < 0:
            return None
        attributes = _meta_attributes(prefix[name_end:tag_end])
        direct_charset = attributes.get(b"charset")
        if direct_charset is not None:
            return _ascii_label(direct_charset)
        if _ascii_label(attributes.get(b"http-equiv", b"")) == "content-type":
            content_charset = _content_charset(attributes.get(b"content", b""))
            if content_charset is not None:
                return content_charset
        search_start = tag_end + 1


def _decode_with_label(body: bytes, label: str) -> str:
    if label in CHARSET_ALLOWLIST:
        return body.decode(label, errors="replace")
    return body.decode("utf-8", errors="replace")


def decode_body(
    body: bytes,
    content_type_header: str | None,
    limits: Limits,
) -> str:
    """Decode bytes using an allowlisted charset without raising."""
    http_label = _http_charset(content_type_header)
    if http_label is not None:
        return _decode_with_label(body, http_label)
    prescan_label = _prescan_charset(body, limits.max_charset_prescan_bytes)
    if prescan_label is not None:
        return _decode_with_label(body, prescan_label)
    return body.decode("utf-8", errors="replace")
