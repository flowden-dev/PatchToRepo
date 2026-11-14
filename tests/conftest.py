import os
import subprocess
from pathlib import Path

import pytest

from patchtorepo.engine import Engine
from patchtorepo.git import Git

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repository with spaces ü &"
    path.mkdir()
    run(path, "init", "-q")
    run(path, "config", "commit.gpgSign", "false")
    hooks = tmp_path / "empty-hooks"
    hooks.mkdir()
    run(path, "config", "core.hooksPath", str(hooks))
    run(path, "config", "user.name", "Test")
    run(path, "config", "user.email", "test@example.invalid")
    run(path, "config", "core.autocrlf", "false")
    (path / "hello.cpp").write_bytes(b"int main() {\n    return 1;\n}\n")
    run(path, "add", ".")
    run(path, "commit", "-qm", "base")
    return path


@pytest.fixture
def engine(tmp_path):
    return Engine(Git(), tmp_path / "application-data")


@pytest.fixture
def patch(repo):
    from patchtorepo.patch import Patch

    (repo / "hello.cpp").write_bytes(b"int main() {\n    return 2;\n}\n")
    raw = run(repo, "diff", "--binary")
    run(repo, "checkout", "--", "hello.cpp")
    return Patch.parse(raw, "hello.patch")
