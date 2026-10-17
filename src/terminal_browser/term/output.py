from __future__ import annotations

import sys
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ..core.errors import OutputError
from ..core.sanitize import sanitize_text
from ..core.text import display_width


class WriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    lines: tuple[str, ...]
    width: int
    stream: Literal["stdout", "stderr"]


class WriteResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    bytes_written: int
    lines_written: int


class Terminal(Protocol):
    def write(self, request: WriteRequest) -> WriteResult: ...
    def sanitize(self, text: str) -> str: ...


class TerminalImpl:
    def write(self, request: WriteRequest) -> WriteResult:
        rendered = "".join(
            f"{_hard_cut(sanitize_text(line), request.width)}\n"
            for line in request.lines
        )
        payload = rendered.encode("utf-8")
        try:
            stream = sys.stdout if request.stream == "stdout" else sys.stderr
            stream.buffer.write(payload)
            stream.buffer.flush()
        except OSError as error:
            raise OutputError("terminal output failed") from error
        return WriteResult(
            bytes_written=len(payload),
            lines_written=len(request.lines),
        )

    def sanitize(self, text: str) -> str:
        return sanitize_text(text)


TerminalOutput = TerminalImpl


def _hard_cut(text: str, width: int) -> str:
    if width <= 0 or display_width(text) <= width:
        return "" if width <= 0 else text
    current = ""
    for character in text:
        character_width = display_width(character)
        if current and display_width(current) + character_width > width:
            break
        current += character
    return current
