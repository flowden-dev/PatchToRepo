"""Disposable fixture for exercising a packaged app without touching user data."""

from pathlib import Path

from .git import Git


def fixture(folder: Path) -> tuple[Path, Path]:
    repo = folder / "sample-repository"
    repo.mkdir()
    git = Git()
    git.run(repo, "init", "-q").require()
    git.run(repo, "config", "commit.gpgSign", "false").require()
    git.run(repo, "config", "core.autocrlf", "false").require()
    hooks = folder / "empty-hooks"
    hooks.mkdir()
    git.run(repo, "config", "core.hooksPath", str(hooks)).require()
    git.run(repo, "config", "user.name", "Package test").require()
    git.run(repo, "config", "user.email", "test@example.invalid").require()
    (repo / "sample.cpp").write_bytes(b"int main() {\n    return 1;\n}\n")
    git.run(repo, "add", ".").require()
    git.run(repo, "commit", "-qm", "test fixture").require()
    patch = folder / "test.patch"
    patch.write_bytes(
        b"diff --git a/sample.cpp b/sample.cpp\n--- a/sample.cpp\n+++ b/sample.cpp\n@@ -1,3 +1,3 @@\n int main() {\n-    return 1;\n+    return 2;\n }\n"
    )
    return repo, patch
