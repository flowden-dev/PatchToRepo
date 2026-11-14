"""Shell-free Git execution with explicit environment and output limits."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .patch import PatchError

MAX_OUTPUT = 8 * 1024 * 1024


class GitError(PatchError):
    pass


@dataclass(frozen=True)
class Result:
    code: int
    stdout: bytes
    stderr: bytes

    @property
    def detail(self) -> str:
        return (self.stderr + self.stdout).decode("utf-8", "replace").strip()

    def require(self) -> Result:
        if self.code:
            raise GitError(self.detail or f"Git exited with code {self.code}.")
        return self


def environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", LC_ALL="C", LANG="C"
    )
    return env


def find_git(saved: str = "") -> str:
    candidates = [saved] if saved else []
    exe = "git.exe" if os.name == "nt" else "git"
    if os.name == "nt":
        for root in (
            os.environ.get("ProgramW6432"),
            os.environ.get("ProgramFiles"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if root:
                for suffix in ("Git/cmd/git.exe", "Programs/Git/cmd/git.exe"):
                    candidates.append(str(Path(root) / suffix))
    for directory in os.get_exec_path():
        if Path(directory).is_absolute():
            candidate = shutil.which(exe, path=directory)
            if candidate:
                candidates.append(candidate)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.is_file():
            return str(path.resolve())
    raise GitError(
        "Git was not found. Install Git for Windows or choose its executable in Settings."
    )


class Git:
    def __init__(self, executable: str = ""):
        self.executable = find_git(executable)
        version = self.run(None, "--version").require().stdout
        if not version.startswith(b"git version "):
            raise GitError("The selected executable did not identify itself as Git.")

    def run(
        self,
        cwd: Path | None,
        *args: str,
        data: bytes | None = None,
        timeout: int = 45,
        max_output: int = MAX_OUTPUT,
    ) -> Result:
        command = [
            self.executable,
            "--no-pager",
            "-c",
            "core.quotePath=false",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "apply.ignoreWhitespace=no",
            "-c",
            "apply.whitespace=warn",
            *args,
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                process = subprocess.run(
                    command,
                    cwd=cwd,
                    input=data,
                    stdout=out,
                    stderr=err,
                    env=environment(),
                    timeout=timeout,
                    creationflags=flags,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitError(
                    "Git timed out. If this happened during Apply, inspect the recovery bundle and working files before retrying."
                ) from exc
            except OSError as exc:
                raise GitError(f"Git could not start: {exc}") from exc
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read(max_output + 1), err.read(MAX_OUTPUT + 1)
        if len(stdout) > max_output or len(stderr) > MAX_OUTPUT:
            raise GitError(
                f"Git output exceeded its limit ({max_output // (1024 * 1024)} MiB stdout / 8 MiB stderr); operation status needs inspection."
            )
        return Result(process.returncode, stdout, stderr)

    def apply(
        self,
        root: Path,
        data: bytes,
        *options: str,
        sandbox: bool = False,
        git_dir: Path | None = None,
        filters: tuple[str, ...] = (),
        attributes_file: Path | None = None,
    ) -> Result:
        settings = []
        for name in filters:
            # attribute checks refuse these drivers; also suppress execution during trial writes
            for key, value in (
                ("clean", ""),
                ("smudge", ""),
                ("process", ""),
                ("required", "false"),
            ):
                settings.extend(("-c", f"filter.{name}.{key}={value}"))
        if git_dir is not None:
            settings.extend((f"--git-dir={git_dir}", f"--work-tree={root}"))
        if attributes_file is not None:
            settings.extend(("-c", f"core.attributesFile={attributes_file}"))
        return self.run(
            root,
            *settings,
            "apply",
            "--whitespace=warn",
            "-p1",
            *(["--no-index"] if sandbox and git_dir is None else []),
            *options,
            "-",
            data=data,
            timeout=120 if "--check" not in options else 45,
        )
