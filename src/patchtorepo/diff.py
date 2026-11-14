"""Bounded, lazy side-by-side alignment and language-aware syntax spans."""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from .engine import FileState

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_LINES = 20000
MAX_LINE_LENGTH = 10000
MAX_SYNTAX_BYTES = 512 * 1024


@dataclass(frozen=True)
class Span:
    start: int
    length: int
    color: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Line:
    text: str
    number: int | None
    kind: str = "equal"
    syntax: tuple[Span, ...] = ()
    emphasis: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Rendered:
    left: tuple[Line, ...]
    right: tuple[Line, ...]
    changes: tuple[int, ...]
    note: str
    limited: bool = False


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def decode(content: bytes, encoding: str) -> tuple[str, str]:
    if encoding != "Auto":
        return content.decode(encoding, "replace"), encoding
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16", "replace"), "UTF-16"
    try:
        return content.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        try:
            return content.decode("cp1252"), "Windows-1252 (auto fallback)"
        except UnicodeDecodeError:
            return content.decode("latin-1"), "Latin-1 (auto fallback)"


def display_text(text: str) -> str:
    # Qt treats paragraph separators and NBSP specially; expose them without changing bytes
    return "".join(
        f"⟦U+{ord(c):04X}⟧"
        if c not in "\n\t"
        and (unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") or c == "\u00a0")
        else c
        for c in text
    )


def file_description(state: FileState, encoding: str, text: str | None = None) -> str:
    data = state.content
    if data is None:
        return "Absent"
    crlf = text.count("\r\n") if text is not None else data.count(b"\r\n")
    lf = (text.count("\n") if text is not None else data.count(b"\n")) - crlf
    endings = (
        "CRLF"
        if crlf and not lf
        else "LF"
        if lf and not crlf
        else "Mixed EOL"
        if crlf or lf
        else "No line breaks"
    )
    has_eol = text.endswith("\n") if text is not None else data.endswith(b"\n")
    eof = "" if not data or has_eol else " · no final newline"
    return f"{len(data):,} bytes · {encoding} · {endings}{eof}"


def _syntax(text: str, filename: str) -> list[tuple[Span, ...]]:
    rows: list[list[Span]] = [[] for _ in text.split("\n")]
    if len(text) > MAX_SYNTAX_BYTES:
        return [() for _ in rows]
    try:
        lexer = get_lexer_for_filename(filename, stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False)
    style = get_style_by_name("monokai")
    row, column = 0, 0
    for token, value in lex(text, lexer):
        spec = style.style_for_token(token)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            length = utf16_length(part)
            if length and row < len(rows) and spec["color"]:
                rows[row].append(
                    Span(column, length, "#" + spec["color"], spec["bold"], spec["italic"])
                )
            column += length
            if i < len(parts) - 1:
                row += 1
                column = 0
    return [tuple(row) for row in rows]


def _characters(
    old: str, new: str
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    if max(len(old), len(new)) > 1200:
        return (), ()
    a, b = [], []
    for tag, i, j, k, n in difflib.SequenceMatcher(None, old, new, autojunk=True).get_opcodes():
        if tag != "equal":
            if i != j:
                a.append((utf16_length(old[:i]), utf16_length(old[i:j])))
            if k != n:
                b.append((utf16_length(new[:k]), utf16_length(new[k:n])))
    return tuple(a), tuple(b)


def render(before: FileState, after: FileState, filename: str, encoding: str = "Auto") -> Rendered:
    old, new = before.content or b"", after.content or b""
    is_binary = any(b"\0" in v and not v.startswith((b"\xff\xfe", b"\xfe\xff")) for v in (old, new))
    if is_binary or max(len(old), len(new)) > MAX_TEXT_BYTES:
        reason = (
            "Binary content"
            if is_binary
            else "Large file: code preview is limited to 2 MiB per side"
        )
        a = f"{file_description(before, 'raw bytes')}\nSHA-256: {before.digest or 'absent'}"
        b = f"{file_description(after, 'raw bytes')}\nSHA-256: {after.digest or 'absent'}"
        return Rendered(
            tuple(Line(s, None) for s in a.splitlines()),
            tuple(Line(s, None) for s in b.splitlines()),
            (),
            reason,
            True,
        )
    a, enc_a = decode(old, encoding)
    b, enc_b = decode(new, encoding)
    note = f"Before: {file_description(before, enc_a, a)}   |   After: {file_description(after, enc_b, b)}"
    a, b = a.replace("\r\n", "\n"), b.replace("\r\n", "\n")
    shown_a, shown_b = display_text(a), display_text(b)
    if (shown_a, shown_b) != (a, b):
        note += " · Control/format characters shown as ⟦U+…⟧ labels"
    a, b = shown_a, shown_b
    left = a.removesuffix("\n").split("\n") if a else []
    right = b.removesuffix("\n").split("\n") if b else []
    if (
        len(left) > MAX_LINES
        or len(right) > MAX_LINES
        or any(len(s) > MAX_LINE_LENGTH for s in left + right)
    ):
        return Rendered(
            (Line("Code preview exceeds the line/length limit.", None),),
            (Line("Use Patch source and file metadata to inspect this change.", None),),
            (),
            note,
            True,
        )
    syntax_a, syntax_b = _syntax(a, filename), _syntax(b, filename)
    out_a: list[Line] = []
    out_b: list[Line] = []
    starts = []
    for tag, i, j, k, n in difflib.SequenceMatcher(None, left, right, autojunk=True).get_opcodes():
        if tag != "equal":
            starts.append(len(out_a))
        for offset in range(max(j - i, n - k)):
            ai, bi = i + offset, k + offset
            x, y = left[ai] if ai < j else "", right[bi] if bi < n else ""
            ex, ey = _characters(x, y) if tag == "replace" else ((), ())
            out_a.append(
                Line(
                    x,
                    ai + 1 if ai < j else None,
                    "equal" if tag == "equal" else "removed" if ai < j else "gap",
                    syntax_a[ai] if ai < j else (),
                    ex,
                )
            )
            out_b.append(
                Line(
                    y,
                    bi + 1 if bi < n else None,
                    "equal" if tag == "equal" else "added" if bi < n else "gap",
                    syntax_b[bi] if bi < n else (),
                    ey,
                )
            )
    if old != new and not starts:
        note += " · Byte-level or line-ending change; see Patch source"
    if before.mode != after.mode:
        note += f" · Mode {before.mode:o} → {after.mode:o}"
    if len(a) > MAX_SYNTAX_BYTES or len(b) > MAX_SYNTAX_BYTES:
        note += " · Syntax coloring limited above 512 KiB"
    return Rendered(tuple(out_a), tuple(out_b), tuple(starts), note)
