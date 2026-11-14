"""Bound compressed binary payloads before handing them to Git."""

from __future__ import annotations

import base64
import re
import zlib

from .patch import PatchError

LIMIT = 32 * 1024 * 1024


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 64, 7):
        if offset >= len(data):
            break
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
    raise PatchError("Invalid Git binary delta size.")


def validate_binary(raw: bytes) -> int:
    """Validate framing and bounded expansion, returning total result sizes."""
    lines = raw.split(b"\n")
    index, count, total = 0, 0, 0
    while index < len(lines):
        line = lines[index].rstrip(b"\r")
        match = re.fullmatch(rb"(literal|delta) ([0-9]+)", line)
        index += 1
        if not match:
            continue
        size = int(match[2])
        if size > LIMIT:
            raise PatchError("Git binary payload exceeds the 32 MiB/file limit.")
        compressed = bytearray()
        while index < len(lines) and lines[index].rstrip(b"\r"):
            line = lines[index].rstrip(b"\r")
            index += 1
            first = line[0]
            length = (
                first - 65 + 1
                if 65 <= first <= 90
                else first - 97 + 27
                if 97 <= first <= 122
                else 0
            )
            if not length or len(line) - 1 != ((length + 3) // 4) * 5:
                raise PatchError("Invalid Git binary payload framing.")
            try:
                compressed.extend(base64.b85decode(line[1:])[:length])
            except ValueError as exc:
                raise PatchError("Invalid Git binary base85 payload.") from exc
        try:
            decoder = zlib.decompressobj()
            inflated = decoder.decompress(compressed, size + 1)
        except zlib.error as exc:
            raise PatchError("Invalid compressed Git binary payload.") from exc
        if (
            len(inflated) != size
            or not decoder.eof
            or decoder.unconsumed_tail
            or decoder.unused_data
        ):
            raise PatchError("Git binary payload size does not match its header.")
        output_size = size
        if match[1] == b"delta":
            source_size, offset = _varint(inflated, 0)
            output_size, _ = _varint(inflated, offset)
            if max(source_size, output_size) > LIMIT:
                raise PatchError("Git binary delta expands beyond the 32 MiB/file limit.")
        total += output_size
        count += 1
    if count not in (1, 2):
        raise PatchError("Expected one or two Git binary payloads per file.")
    return total
