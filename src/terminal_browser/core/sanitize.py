# Unicode 16.0.0 Cf ranges removed: U+00AD; U+0600–U+0605; U+061C; U+06DD;
# U+070F; U+0890–U+0891; U+08E2; U+180E; U+200B–U+200F; U+202A–U+202E;
# U+2060–U+2064; U+2066–U+206F; U+FEFF; U+FFF9–U+FFFB; U+110BD; U+110CD;
# U+13430–U+1343F; U+1BCA0–U+1BCA3; U+1D173–U+1D17A; U+E0001; U+E0020–U+E007F.

import unicodedata


def _is_removed(character: str) -> bool:
    codepoint = ord(character)
    if codepoint <= 0x1F and character not in "\n\t":
        return True
    if codepoint == 0x7F or 0x80 <= codepoint <= 0x9F:
        return True
    return unicodedata.category(character) == "Cf"


def sanitize_text(text: str) -> str:
    return "".join(
        character
        for character in text
        if character in "\n\t" or not _is_removed(character)
    )


def sanitize_attribute(value: str) -> str:
    sanitized: list[str] = []
    for character in value:
        if character == "\n" or character == "\t":
            sanitized.append(" ")
        elif not _is_removed(character):
            sanitized.append(character)
    return "".join(sanitized)
