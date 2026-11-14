import base64
import random
import zlib

import pytest
from conftest import run

from patchtorepo.binary import validate_binary
from patchtorepo.patch import Patch, PatchError


def payload(kind, data, declared=None):
    compressed = zlib.compress(data)
    lines = []
    for start in range(0, len(compressed), 52):
        part = compressed[start : start + 52]
        size = len(part)
        marker = bytes([64 + size if size <= 26 else 96 + size - 26])
        lines.append(marker + base64.b85encode(part, pad=True))
    return (
        kind
        + b" "
        + str(len(data) if declared is None else declared).encode()
        + b"\n"
        + b"\n".join(lines)
        + b"\n\n"
    )


def varint(size):
    output = bytearray()
    while size >= 128:
        output.append((size & 127) | 128)
        size >>= 7
    output.append(size)
    return bytes(output)


def test_oversized_compressed_literal_is_rejected():
    with pytest.raises(PatchError, match="size"):
        validate_binary(payload(b"literal", b"x" * 10000, declared=10))


def test_delta_target_bound_is_checked_before_git():
    with pytest.raises(PatchError, match="expands"):
        validate_binary(payload(b"delta", varint(12) + varint(100 * 1024 * 1024)))


def test_real_git_delta_patch(engine, repo):
    rng = random.Random(100)
    before = rng.randbytes(65536)
    file = repo / "delta.bin"
    file.write_bytes(before)
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "binary delta")
    after = before[:500] + b"new data" + before[508:]
    file.write_bytes(after)
    raw = run(repo, "diff", "--binary")
    assert b"\ndelta " in raw
    patch = Patch.parse(raw)
    run(repo, "checkout", "--", "delta.bin")
    assert engine.apply(engine.review(repo, patch)).verified
    assert file.read_bytes() == after
