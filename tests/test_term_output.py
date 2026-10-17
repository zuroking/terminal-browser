import ast
import io
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from terminal_browser.core.errors import OutputError
from terminal_browser.term.output import TerminalImpl, WriteRequest


class FailingBuffer:
    def write(self, data: bytes) -> int:
        raise OSError("write failed")

    def flush(self) -> None:
        return None


def set_streams(monkeypatch: pytest.MonkeyPatch, stdout: io.BytesIO, stderr: io.BytesIO) -> None:
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=stdout))
    monkeypatch.setattr(sys, "stderr", SimpleNamespace(buffer=stderr))


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "term" / "output.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"__future__", "sys", "typing", "pydantic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_stdlib
            else:
                assert node.level == 2
                assert node.module in {"core.errors", "core.sanitize", "core.text"}


def test_egress_sanitizer_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.BytesIO()
    set_streams(monkeypatch, stdout, io.BytesIO())
    result = TerminalImpl().write(
        WriteRequest(
            lines=("a\x00b\x1bc\u202ed\u200b",),
            width=40,
            stream="stdout",
        )
    )
    assert stdout.getvalue() == b"abcd\n"
    assert result.lines_written == 1


def test_hard_cut_overwidth_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.BytesIO()
    set_streams(monkeypatch, stdout, io.BytesIO())
    result = TerminalImpl().write(
        WriteRequest(lines=("abcdef",), width=4, stream="stdout")
    )
    assert stdout.getvalue() == b"abcd\n"
    assert result.bytes_written == 5


def test_stdout_and_stderr_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.BytesIO()
    stderr = io.BytesIO()
    set_streams(monkeypatch, stdout, stderr)
    terminal = TerminalImpl()
    terminal.write(WriteRequest(lines=("out",), width=10, stream="stdout"))
    terminal.write(WriteRequest(lines=("err",), width=10, stream="stderr"))
    assert stdout.getvalue() == b"out\n"
    assert stderr.getvalue() == b"err\n"


def test_utf8_encoding_and_byte_count(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.BytesIO()
    set_streams(monkeypatch, stdout, io.BytesIO())
    result = TerminalImpl().write(
        WriteRequest(lines=("é😀",), width=10, stream="stdout")
    )
    assert stdout.getvalue() == "é😀\n".encode("utf-8")
    assert result.bytes_written == len(stdout.getvalue())
    assert result.lines_written == 1


def test_terminal_sanitize_method() -> None:
    assert TerminalImpl().sanitize("a\x00b\u202ec") == "abc"


def test_output_error_on_io_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=FailingBuffer()))
    with pytest.raises(OutputError):
        TerminalImpl().write(
            WriteRequest(lines=("failure",), width=20, stream="stdout")
        )
