"""Conservative patch inventory; Git still validates every hunk."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

MAX_PATCH_BYTES = 32 * 1024 * 1024
MAX_FILES = 2000


class PatchError(ValueError):
    """An input cannot be safely reviewed or applied."""


def unquote(value: bytes) -> str:
    if value.startswith(b'"'):
        if not value.endswith(b'"'):
            raise PatchError("Unterminated quoted filename.")
        value = value[1:-1]
        output = bytearray()
        i = 0
        escapes = {
            ord("t"): 9,
            ord("n"): 10,
            ord("r"): 13,
            ord("b"): 8,
            ord("f"): 12,
            ord("v"): 11,
            ord("a"): 7,
            ord('"'): 34,
            92: 92,
        }
        while i < len(value):
            c = value[i]
            i += 1
            if c != 92:
                output.append(c)
                continue
            if i == len(value):
                raise PatchError("Incomplete filename escape.")
            c = value[i]
            if 48 <= c <= 55:
                match = re.match(rb"[0-7]{1,3}", value[i:])
                assert match
                n = int(match[0], 8)
                if n > 255:
                    raise PatchError("Invalid filename escape.")
                output.append(n)
                i += len(match[0])
            elif c in escapes:
                output.append(escapes[c])
                i += 1
            else:
                raise PatchError("Unsupported filename escape.")
        value = bytes(output)
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(
            "Filenames must use UTF-8. File contents may use other encodings."
        ) from exc


def safe_path(value: str) -> str:
    parts = value.split("/")
    if not value or any(p in ("", ".", "..") for p in parts):
        raise PatchError(f"Unsafe path: {value!r}")
    for part in parts:
        if (
            part.casefold() == ".git"
            or part.endswith((" ", "."))
            or any(ord(c) < 32 or c in '\\:*?"<>|\x7f' for c in part)
            or re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(?:\..*)?", part)
        ):
            raise PatchError(f"Unsupported or unsafe path: {value!r}")
    return value


def path_field(value: bytes, strip: int = 0) -> str | None:
    name = unquote(value)
    if name == "/dev/null":
        return None
    parts = name.split("/")
    if len(parts) <= strip:
        raise PatchError(f"Filename has too few path components: {name!r}")
    return safe_path("/".join(parts[strip:]))


def header_paths(line: bytes) -> tuple[str, str]:
    raw = line[len(b"diff --git ") :]
    candidates = []
    for m in re.finditer(b" ", raw):
        try:
            a, b = unquote(raw[: m.start()]), unquote(raw[m.end() :])
        except PatchError:
            continue
        if a.startswith("a/") and b.startswith("b/"):
            try:
                candidates.append((safe_path(a[2:]), safe_path(b[2:])))
            except PatchError:
                continue
    same = [pair for pair in candidates if pair[0] == pair[1]]
    if len(same) == 1:
        return same[0]
    if len(candidates) == 1:
        return candidates[0]
    raise PatchError("Unsupported diff header. Use Git's default a/ and b/ prefixes.")


@dataclass(frozen=True)
class FileChange:
    old: str | None
    new: str | None
    kind: str
    added: int
    removed: int
    binary: bool
    old_mode: str | None
    new_mode: str | None
    raw: bytes

    @property
    def path(self) -> str:
        return self.new or self.old or ""

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(p for p in (self.old, self.new) if p))


@dataclass(frozen=True)
class Patch:
    name: str
    data: bytes
    files: tuple[FileChange, ...]
    strip: int = 1

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(p for f in self.files for p in f.paths))

    @classmethod
    def read(cls, path: Path) -> Patch:
        with path.open("rb") as stream:
            data = stream.read(MAX_PATCH_BYTES + 1)
        return cls.parse(data, path.name)

    @classmethod
    def parse(cls, data: bytes, name: str = "Untitled.patch") -> Patch:
        if not data or len(data) > MAX_PATCH_BYTES:
            raise PatchError("Choose a nonempty patch of at most 32 MiB.")
        if b"\x00" in data:
            raise PatchError("This is not a text/Git binary patch (contains NUL bytes).")
        if re.search(rb"(?m)^diff --(?:cc|combined) ", data):
            raise PatchError("Combined merge diffs are unsupported. Export an ordinary Git diff.")
        starts = list(re.finditer(rb"(?m)^diff --git ", data))
        if not starts:
            raise PatchError("Use a Git-format patch with 'diff --git' file headers.")
        if len(starts) > MAX_FILES:
            raise PatchError(f"A patch may contain at most {MAX_FILES:,} files.")
        changes = []
        binary_total = 0
        seen: dict[str, int] = {}
        for i, start in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(data)
            change = _parse_block(data[start.start() : end])
            if change.binary:
                from .binary import validate_binary

                binary_total += validate_binary(change.raw)
                if binary_total > 256 * 1024 * 1024:
                    raise PatchError("Binary payloads exceed the 256 MiB review limit.")
            for path in change.paths:
                key = path.casefold()
                if key in seen and seen[key] != i:
                    raise PatchError(
                        "Repeated or overlapping paths are unsupported. Export one cumulative diff."
                    )
                seen[key] = i
            if (
                change.old
                and change.new
                and change.old != change.new
                and change.old.casefold() == change.new.casefold()
            ):
                raise PatchError("Case-only renames are unsupported; use your Git client.")
            changes.append(change)
        keys = set(seen)
        for key in keys:
            parts = key.split("/")
            if any("/".join(parts[:i]) in keys for i in range(1, len(parts))):
                raise PatchError(
                    "File/directory replacements are unsupported; use your Git client."
                )
        return cls(name, data, tuple(changes))


def _parse_block(raw: bytes) -> FileChange:
    lines = raw.split(b"\n")
    old, new = header_paths(lines[0].rstrip(b"\r"))
    original = (old, new)
    kind, old_mode, new_mode = "Modified", None, None
    binary, in_header = False, True
    added = removed = 0
    old_left = new_left = 0
    declared_old = declared_new = False
    for line in lines[1:]:
        header = line.rstrip(b"\r")
        if not binary and not old_left and not new_left and header == b"-- ":
            break
        if not binary and header.startswith(b"@@"):
            if old_left or new_left:
                raise PatchError("Hunk ended before its declared line counts were satisfied.")
            hunk = re.match(rb"@@ -[0-9]+(?:,([0-9]+))? \+[0-9]+(?:,([0-9]+))? @@", header)
            if not hunk:
                raise PatchError("Invalid unified diff hunk header.")
            try:
                old_left, new_left = (
                    int(value) if value is not None else 1 for value in hunk.groups()
                )
            except ValueError as exc:
                raise PatchError("Invalid hunk line count.") from exc
            in_header = False
            continue
        if in_header and header == b"GIT binary patch":
            binary, in_header = True, False
        if in_header:
            if header.startswith(b"Binary files "):
                raise PatchError("Binary diff has no payload. Export with git diff --binary.")
            if re.match(rb"(?:new file|deleted file|old|new) mode ", header):
                mode = header.rsplit(b" ", 1)[1].decode("ascii", "replace")
                if mode not in ("100644", "100755"):
                    raise PatchError("Submodules, symlinks and special file modes are unsupported.")
                if header.startswith(b"new file mode "):
                    old, kind, new_mode = None, "Added", mode
                elif header.startswith(b"deleted file mode "):
                    new, kind, old_mode = None, "Deleted", mode
                elif header.startswith(b"old mode "):
                    old_mode = mode
                else:
                    new_mode = mode
            elif header.startswith(b"index "):
                mode = header.split(b" ")[-1]
                if mode in (b"120000", b"160000"):
                    raise PatchError("Submodule and symlink patches are unsupported.")
            elif header.startswith((b"rename from ", b"copy from ")):
                prefix = b"rename from " if header.startswith(b"rename") else b"copy from "
                if path_field(header[len(prefix) :]) != original[0]:
                    raise PatchError("Inconsistent source path in patch headers.")
                kind = "Renamed" if prefix.startswith(b"rename") else "Copied"
            elif header.startswith((b"rename to ", b"copy to ")):
                prefix = b"rename to " if header.startswith(b"rename") else b"copy to "
                if path_field(header[len(prefix) :]) != original[1]:
                    raise PatchError("Inconsistent destination path in patch headers.")
            elif header.startswith(b"--- "):
                value = path_field(header[4:].split(b"\t")[0], 1)
                if value != old:
                    raise PatchError("Inconsistent before path in patch headers.")
                declared_old = True
            elif header.startswith(b"+++ "):
                value = path_field(header[4:].split(b"\t")[0], 1)
                if value != new:
                    raise PatchError("Inconsistent after path in patch headers.")
                declared_new = True
        elif not binary and (old_left or new_left):
            if header == b"\\ No newline at end of file":
                continue
            if line.startswith(b"+"):
                added += 1
                new_left -= 1
            elif line.startswith(b"-"):
                removed += 1
                old_left -= 1
            elif line.startswith(b" "):
                old_left -= 1
                new_left -= 1
            else:
                raise PatchError("Invalid or truncated hunk body.")
            if old_left < 0 or new_left < 0:
                raise PatchError("Hunk body exceeds its declared line counts.")
        elif not binary and not in_header and line.startswith((b"+", b"-", b" ", b"\\")):
            if header != b"\\ No newline at end of file":
                raise PatchError("Unexpected hunk content outside its declared line counts.")
    if old_left or new_left:
        raise PatchError("Hunk ended before its declared line counts were satisfied.")
    if not binary and (added or removed) and not (declared_old and declared_new):
        raise PatchError("Missing text diff headers.")
    if old != new and old and new and kind not in ("Renamed", "Copied"):
        raise PatchError("Different filenames require explicit rename/copy headers.")
    return FileChange(old, new, kind, added, removed, binary, old_mode, new_mode, raw)
