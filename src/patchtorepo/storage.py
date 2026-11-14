"""Transactional preferences, repository history and process coordination."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .patch import PatchError


def data_directory() -> Path:
    override = os.environ.get("PATCHTOREPO_DATA")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "PatchToRepo"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "patch-to-repo"


def path_key(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


class Store:
    def __init__(self, folder: Path | None = None):
        self.folder = folder or data_directory()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.folder / "preferences.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS repositories (
                    path_key TEXT PRIMARY KEY, path TEXT NOT NULL, used REAL NOT NULL
                );
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value: Any) -> None:
        self.set_many({key: value})

    def set_many(self, values: dict[str, Any]) -> None:
        rows = [(key, json.dumps(value)) for key, value in values.items()]
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", rows)

    def repos(self) -> list[str]:
        with self.connect() as db:
            return [
                r[0] for r in db.execute("SELECT path FROM repositories ORDER BY used DESC, path")
            ]

    def remember(self, path: Path | str) -> None:
        import time

        resolved = Path(path).resolve()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO repositories VALUES (?, ?, ?)",
                (path_key(resolved), str(resolved), time.time()),
            )
            db.execute(
                "DELETE FROM repositories WHERE path_key NOT IN "
                "(SELECT path_key FROM repositories ORDER BY used DESC LIMIT 50)"
            )

    def forget(self, path: Path | str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM repositories WHERE path_key=?", (path_key(path),))

    def import_legacy(self) -> int:
        if os.name != "nt" or self.get("legacy_imported", False):
            return 0
        import winreg

        repos: list[str] = []
        git = ""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\PatchToRepo",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "RecentRepos")
                    repos = value if isinstance(value, list) else value.splitlines()
                except FileNotFoundError:
                    pass
                try:
                    git, _ = winreg.QueryValueEx(key, "GitExe")
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        for repo in reversed(repos[:50]):
            if isinstance(repo, str) and Path(repo).is_absolute():
                self.remember(repo)
        if isinstance(git, str) and git and not self.get("git"):
            self.set("git", git)
        self.set("legacy_imported", True)
        return len(repos)


@contextmanager
def repository_lock(folder: Path, root: Path):
    """OS-held lock: automatically released if a process dies."""
    lock_dir = folder / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(path_key(root).encode("utf-8")).hexdigest() + ".lock"
    with (lock_dir / name).open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise PatchError(
                "Another Patch to Repo window is applying to this repository."
            ) from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
