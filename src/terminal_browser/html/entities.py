from ..core.limits import Limits


_NAMED_VALUES: dict[str, str] = {
    "quot": '"',
    "AMP": "&",
    "amp": "&",
    "COPY": "©",
    "copy": "©",
    "GT": ">",
    "gt": ">",
    "LT": "<",
    "lt": "<",
    "QUOT": '"',
    "REG": "®",
    "reg": "®",
    "apos": "'",
    "nbsp": "\u00a0",
    "iexcl": "¡",
    "cent": "¢",
    "pound": "£",
    "curren": "¤",
    "yen": "¥",
    "brvbar": "¦",
    "sect": "§",
    "uml": "¨",
    "ordf": "ª",
    "laquo": "«",
    "not": "¬",
    "shy": "\u00ad",
    "macr": "¯",
    "deg": "°",
    "plusmn": "±",
    "sup2": "²",
    "sup3": "³",
    "acute": "´",
    "micro": "µ",
    "para": "¶",
    "middot": "·",
    "cedil": "¸",
    "sup1": "¹",
    "ordm": "º",
    "raquo": "»",
    "frac14": "¼",
    "frac12": "½",
    "frac34": "¾",
    "iquest": "¿",
    "Agrave": "À",
    "Aacute": "Á",
    "Acirc": "Â",
    "Atilde": "Ã",
    "Auml": "Ä",
    "Aring": "Å",
    "AElig": "Æ",
    "Ccedil": "Ç",
    "Egrave": "È",
    "Eacute": "É",
    "Ecirc": "Ê",
    "Euml": "Ë",
    "Igrave": "Ì",
    "Iacute": "Í",
    "Icirc": "Î",
    "Iuml": "Ï",
    "ETH": "Ð",
    "Ntilde": "Ñ",
    "Ograve": "Ò",
    "Oacute": "Ó",
    "Ocirc": "Ô",
    "Otilde": "Õ",
    "Ouml": "Ö",
    "times": "×",
    "Oslash": "Ø",
    "Ugrave": "Ù",
    "Uacute": "Ú",
    "Ucirc": "Û",
    "Uuml": "Ü",
    "Yacute": "Ý",
    "THORN": "Þ",
    "szlig": "ß",
    "agrave": "à",
    "aacute": "á",
    "acirc": "â",
    "atilde": "ã",
    "auml": "ä",
    "aring": "å",
    "aelig": "æ",
    "ccedil": "ç",
    "egrave": "è",
    "eacute": "é",
    "ecirc": "ê",
    "euml": "ë",
    "igrave": "ì",
    "iacute": "í",
    "icirc": "î",
    "iuml": "ï",
    "eth": "ð",
    "ntilde": "ñ",
    "ograve": "ò",
    "oacute": "ó",
    "ocirc": "ô",
    "otilde": "õ",
    "ouml": "ö",
    "divide": "÷",
    "oslash": "ø",
    "ugrave": "ù",
    "uacute": "ú",
    "ucirc": "û",
    "uuml": "ü",
    "yacute": "ý",
    "thorn": "þ",
    "yuml": "ÿ",
    "OElig": "Œ",
    "oelig": "œ",
    "Scaron": "Š",
    "scaron": "š",
    "Yuml": "Ÿ",
    "fnof": "ƒ",
    "circ": "ˆ",
    "tilde": "˜",
    "Alpha": "Α",
    "Beta": "Β",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Epsilon": "Ε",
    "Zeta": "Ζ",
    "Eta": "Η",
    "Theta": "Θ",
    "Iota": "Ι",
    "Kappa": "Κ",
    "Lambda": "Λ",
    "Mu": "Μ",
    "Nu": "Ν",
    "Xi": "Ξ",
    "Omicron": "Ο",
    "Pi": "Π",
    "Rho": "Ρ",
    "Sigma": "Σ",
    "Tau": "Τ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Chi": "Χ",
    "Psi": "Ψ",
    "Omega": "Ω",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "omicron": "ο",
    "pi": "π",
    "rho": "ρ",
    "sigmaf": "ς",
    "sigma": "σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "thetasym": "ϑ",
    "upsih": "ϒ",
    "piv": "ϖ",
    "ensp": " ",
    "emsp": " ",
    "thinsp": " ",
    "zwnj": "‌",
    "zwj": "‍",
    "lrm": "‎",
    "rlm": "‏",
    "ndash": "–",
    "mdash": "—",
    "lsquo": "‘",
    "rsquo": "’",
    "sbquo": "‚",
    "ldquo": "“",
    "rdquo": "”",
    "bdquo": "„",
    "dagger": "†",
    "Dagger": "‡",
    "bull": "•",
    "hellip": "…",
    "permil": "‰",
    "prime": "′",
    "Prime": "″",
    "lsaquo": "‹",
    "rsaquo": "›",
    "oline": "‾",
    "frasl": "⁄",
    "euro": "€",
    "image": "ℑ",
    "weierp": "℘",
    "real": "ℜ",
    "trade": "™",
    "alefsym": "ℵ",
    "larr": "←",
    "uarr": "↑",
    "rarr": "→",
    "darr": "↓",
    "harr": "↔",
    "crarr": "↵",
    "lArr": "⇐",
    "uArr": "⇑",
    "rArr": "⇒",
    "dArr": "⇓",
    "hArr": "⇔",
    "forall": "∀",
    "part": "∂",
    "exist": "∃",
    "empty": "∅",
    "nabla": "∇",
    "isin": "∈",
    "notin": "∉",
    "ni": "∋",
    "prod": "∏",
    "sum": "∑",
    "minus": "−",
    "lowast": "∗",
    "radic": "√",
    "prop": "∝",
    "infin": "∞",
    "ang": "∠",
    "and": "∧",
    "or": "∨",
    "cap": "∩",
    "cup": "∪",
    "int": "∫",
    "there4": "∴",
    "sim": "∼",
    "cong": "≅",
    "asymp": "≈",
    "ne": "≠",
    "equiv": "≡",
    "le": "≤",
    "ge": "≥",
    "sub": "⊂",
    "sup": "⊃",
    "nsub": "⊄",
    "sube": "⊆",
    "supe": "⊇",
    "oplus": "⊕",
    "otimes": "⊗",
    "perp": "⊥",
    "sdot": "⋅",
    "lceil": "⌈",
    "rceil": "⌉",
    "lfloor": "⌊",
    "rfloor": "⌋",
    "loz": "◊",
    "spades": "♠",
    "clubs": "♣",
    "hearts": "♥",
    "diams": "♦",
}

_LEGACY_NAMES = frozenset(
    {
        "AElig",
        "AMP",
        "Aacute",
        "Acirc",
        "Agrave",
        "Aring",
        "Atilde",
        "Auml",
        "COPY",
        "Ccedil",
        "ETH",
        "Eacute",
        "Ecirc",
        "Egrave",
        "Euml",
        "GT",
        "Iacute",
        "Icirc",
        "Igrave",
        "Iuml",
        "LT",
        "Ntilde",
        "Oacute",
        "Ocirc",
        "Ograve",
        "Oslash",
        "Otilde",
        "Ouml",
        "QUOT",
        "REG",
        "THORN",
        "Uacute",
        "Ucirc",
        "Ugrave",
        "Uuml",
        "Yacute",
        "aacute",
        "acirc",
        "acute",
        "aelig",
        "agrave",
        "amp",
        "aring",
        "atilde",
        "auml",
        "brvbar",
        "ccedil",
        "cedil",
        "cent",
        "copy",
        "curren",
        "deg",
        "divide",
        "eacute",
        "ecirc",
        "egrave",
        "eth",
        "euml",
        "frac12",
        "frac14",
        "frac34",
        "gt",
        "iacute",
        "icirc",
        "iexcl",
        "igrave",
        "iquest",
        "iuml",
        "laquo",
        "lt",
        "macr",
        "micro",
        "middot",
        "not",
        "ntilde",
        "oacute",
        "ocirc",
        "ograve",
        "ordf",
        "ordm",
        "oslash",
        "otilde",
        "ouml",
        "para",
        "plusmn",
        "pound",
        "quot",
        "raquo",
        "reg",
        "sect",
        "shy",
        "sup1",
        "sup2",
        "sup3",
        "szlig",
        "thorn",
        "times",
        "uacute",
        "ucirc",
        "ugrave",
        "uml",
        "uuml",
        "yacute",
        "yen",
        "yuml",
    }
)

HTML4_ENTITIES: dict[str, tuple[str, bool]] = {
    name: (value, name in _LEGACY_NAMES)
    for name, value in _NAMED_VALUES.items()
}
ENTITY_TABLE = HTML4_ENTITIES


class EntityDecoder:
    def __init__(self, limits: Limits | None = None) -> None:
        self._limits = limits

    def decode_text(self, text: str) -> str:
        return self._decode(text, attribute_context=False)

    def decode_attribute(self, value: str) -> str:
        return self._decode(value, attribute_context=True)

    def _decode(self, text: str, attribute_context: bool) -> str:
        output: list[str] = []
        cursor = 0
        while cursor < len(text):
            ampersand = text.find("&", cursor)
            if ampersand < 0:
                output.append(text[cursor:])
                break
            output.append(text[cursor:ampersand])
            if text.startswith("&#", ampersand):
                numeric = self._decode_numeric(text, ampersand)
                if numeric is not None:
                    decoded, next_cursor = numeric
                    output.append(decoded)
                    cursor = next_cursor
                    continue
            name_start = ampersand + 1
            name_end = name_start
            while name_end < len(text) and _is_name_character(text[name_end]):
                name_end += 1
            if name_end == name_start:
                output.append("&")
                cursor = name_start
                continue
            name = text[name_start:name_end]
            if name_end < len(text) and text[name_end] == ";":
                entity = HTML4_ENTITIES.get(name)
                if entity is not None:
                    output.append(entity[0])
                    cursor = name_end + 1
                else:
                    output.append("&" + name)
                    cursor = name_end
                continue
            legacy_name = _find_legacy_name(name)
            if legacy_name is None:
                output.append("&" + name)
                cursor = name_end
                continue
            next_cursor = name_start + len(legacy_name)
            following = text[next_cursor] if next_cursor < len(text) else ""
            blocked = attribute_context and (
                following == "=" or _is_ascii_alphanumeric(following)
            )
            if blocked:
                output.append("&" + legacy_name)
            else:
                output.append(HTML4_ENTITIES[legacy_name][0])
            cursor = next_cursor
        return "".join(output)

    def _decode_numeric(
        self,
        text: str,
        start: int,
    ) -> tuple[str, int] | None:
        index = start + 2
        base = 10
        if index < len(text) and text[index] in {"x", "X"}:
            base = 16
            index += 1
        digit_start = index
        value = 0
        while index < len(text):
            digit = _digit_value(text[index], base)
            if digit is None:
                break
            if value <= 0x110000:
                value = value * base + digit
            index += 1
        if index == digit_start or index >= len(text) or text[index] != ";":
            return None
        next_cursor = index + 1
        if value > 0x10FFFF:
            return "\ufffd", next_cursor
        if 0xD800 <= value <= 0xDFFF:
            return "\ufffd", next_cursor
        if value <= 0x1F and value not in {0x09, 0x0A, 0x0C, 0x0D}:
            return "\ufffd", next_cursor
        if 0x7F <= value <= 0x9F:
            return "\ufffd", next_cursor
        return chr(value), next_cursor


EntityDecoderImpl = EntityDecoder


def _digit_value(character: str, base: int) -> int | None:
    if "0" <= character <= "9":
        value = ord(character) - ord("0")
    elif "a" <= character <= "f":
        value = ord(character) - ord("a") + 10
    elif "A" <= character <= "F":
        value = ord(character) - ord("A") + 10
    else:
        return None
    return value if value < base else None


def _is_name_character(character: str) -> bool:
    return _is_ascii_alphanumeric(character)


def _is_ascii_alphanumeric(character: str) -> bool:
    return (
        "A" <= character <= "Z"
        or "a" <= character <= "z"
        or "0" <= character <= "9"
    )


def _find_legacy_name(name: str) -> str | None:
    best_name: str | None = None
    for index in range(1, len(name) + 1):
        candidate = name[:index]
        entity = HTML4_ENTITIES.get(candidate)
        if entity is None:
            continue
        if not entity[1]:
            return None
        best_name = candidate
    return best_name
