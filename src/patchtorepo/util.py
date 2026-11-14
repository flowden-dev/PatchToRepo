from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".patch-to-repo-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
