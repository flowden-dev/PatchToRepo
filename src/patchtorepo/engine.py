"""Review actual working files, then apply only the reviewed transformation."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .git import Git
from .patch import Patch, PatchError
from .storage import path_key, repository_lock

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_INDEX_OUTPUT = 64 * 1024 * 1024


@dataclass(frozen=True)
class FileState:
    path: str
    content: bytes | None
    mode: int = 0

    @property
    def digest(self) -> str | None:
        return hashlib.sha256(self.content).hexdigest() if self.content is not None else None


@dataclass(frozen=True)
class RepoState:
    root: Path
    git_dir: Path
    head: bytes
    branch: bytes
    index_digest: str
    config_digest: str
    filter_drivers: tuple[str, ...]
    attributes_file: Path | None
    index_boundaries: frozenset[str]

    @property
    def branch_label(self) -> str:
        return self.branch.decode("utf-8", "replace").strip() or "Detached HEAD"


@dataclass(frozen=True)
class Candidate:
    root: Path
    status: str
    reason: str
    score: int
    branch: str = ""


@dataclass(frozen=True)
class Review:
    patch: Patch
    repo: RepoState
    before: tuple[FileState, ...]
    after: tuple[FileState, ...]
    diagnostics: str
    attribute_digest: str

    def pair(self, index: int) -> tuple[FileState, FileState]:
        change = self.patch.files[index]
        before = next((s for s in self.before if s.path == change.old), FileState("", None))
        after = next((s for s in self.after if s.path == change.new), FileState("", None))
        return before, after


@dataclass(frozen=True)
class Applied:
    backup: Path
    diagnostics: str
    verified: bool


class ApplyError(PatchError):
    def __init__(self, message: str, backup: Path | None = None):
        super().__init__(message)
        self.backup = backup


def _digest_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _safe_target(root: Path, relative: str) -> Path:
    target = root.joinpath(*relative.split("/"))
    current = root
    parts = relative.split("/")
    for i, part in enumerate(parts):
        current = current / part
        try:
            st = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
            raise PatchError(f"Symlink or junction in affected path: {relative}")
        last = i == len(parts) - 1
        if last:
            if not stat.S_ISREG(st.st_mode):
                raise PatchError(f"Affected path is not a regular file: {relative}")
            if st.st_nlink > 1:
                raise PatchError(f"Hard-linked files require manual handling: {relative}")
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise PatchError(f"Parent is not a directory: {relative}")
            if (current / ".git").exists():
                raise PatchError(f"Patch crosses a nested repository: {relative}")
    if not target.resolve().is_relative_to(root):
        raise PatchError(f"Path escapes the repository: {relative}")
    return target


def _read_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
        info.st_nlink,
    )


def snapshot(root: Path, paths: tuple[str, ...]) -> tuple[FileState, ...]:
    result = []
    total = 0
    for relative in paths:
        target = _safe_target(root, relative)
        try:
            before = target.stat()
        except FileNotFoundError:
            result.append(FileState(relative, None))
            continue
        if before.st_size > MAX_FILE_BYTES:
            raise PatchError(f"Affected file exceeds 32 MiB: {relative}")
        with target.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            content = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            # Windows path stat and descriptor fstat can report different ctime values
            # compare each API with itself, and also verify the pathname still exists safely
            try:
                current = _safe_target(root, relative).stat()
            except FileNotFoundError as error:
                raise PatchError(
                    f"File disappeared while being read: {relative}. Run Check again."
                ) from error
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise PatchError("Affected file data exceeds the 32 MiB/file or 256 MiB/review limit.")
        if (
            _read_signature(before) != _read_signature(current)
            or _read_signature(opened) != _read_signature(after)
            or len(content) != after.st_size
            or len(content) != current.st_size
        ):
            raise PatchError(f"File changed while being read: {relative}. Run Check again.")
        result.append(FileState(relative, content, stat.S_IMODE(current.st_mode)))
    return tuple(result)


def attribute_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    result = {".gitattributes"}
    for path in paths:
        parts = path.split("/")
        result.update("/".join((*parts[:i], ".gitattributes")) for i in range(1, len(parts)))
    return tuple(sorted(result))


def validate_boundaries(repo: RepoState, paths: tuple[str, ...]) -> None:
    for path in paths:
        parts = path.casefold().split("/")
        for size in range(1, len(parts) + 1):
            prefix = "/".join(parts[:size])
            if prefix in repo.index_boundaries:
                raise PatchError(
                    f"Affected path crosses an indexed submodule or symlink boundary: {path}"
                )


class Engine:
    def __init__(self, git: Git, data_dir: Path):
        self.git = git
        self.data_dir = data_dir

    def repo_state(self, folder: Path) -> RepoState:
        root_raw = self.git.run(folder, "rev-parse", "--show-toplevel").require().stdout
        root = Path(os.fsdecode(root_raw.rstrip(b"\r\n"))).resolve(strict=True)
        gd = self.git.run(root, "rev-parse", "--absolute-git-dir").require().stdout
        git_dir = Path(os.fsdecode(gd.rstrip(b"\r\n"))).resolve(strict=True)
        entries = (
            self.git.run(root, "ls-files", "--stage", "-z", max_output=MAX_INDEX_OUTPUT)
            .require()
            .stdout
        )
        boundaries = set()
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            metadata, separator, path = entry.partition(b"\t")
            fields = metadata.split()
            if not separator or len(fields) != 3:
                raise PatchError("Git returned an invalid index inventory.")
            mode, _, stage = fields
            if stage != b"0":
                raise PatchError("This repository has unresolved index conflicts.")
            if mode not in (b"100644", b"100755"):
                boundaries.add(path.decode("utf-8", "surrogateescape").casefold())
        for name in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
            "index.lock",
        ):
            if (git_dir / name).exists():
                raise PatchError(f"Finish the active Git operation first ({name}).")
        sparse = self.git.run(root, "config", "--bool", "core.sparseCheckout")
        if sparse.code not in (0, 1):
            sparse.require()
        if sparse.stdout.strip() == b"true":
            raise PatchError("Sparse checkouts are unsupported. Use a full working tree.")
        head_result = self.git.run(root, "rev-parse", "--verify", "--quiet", "HEAD")
        if head_result.code not in (0, 1):
            head_result.require()
        branch = self.git.run(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if branch.code not in (0, 1):
            branch.require()
        config = self.git.run(root, "config", "--null", "--list").require().stdout
        attr_config = self.git.run(root, "config", "--path", "--get", "core.attributesFile")
        if attr_config.code not in (0, 1):
            attr_config.require()
        attr_path = attr_config.stdout.rstrip(b"\r\n")
        attributes_file = (root / os.fsdecode(attr_path)).resolve() if attr_path else None
        drivers = set()
        for entry in config.split(b"\0"):
            key = entry.split(b"\n", 1)[0].decode("utf-8")
            if key.startswith("filter.") and key.rsplit(".", 1)[-1] in (
                "clean",
                "smudge",
                "process",
                "required",
            ):
                drivers.add(key[len("filter.") :].rsplit(".", 1)[0])
        return RepoState(
            root,
            git_dir,
            head_result.stdout,
            branch.stdout,
            _digest_file(git_dir / "index"),
            hashlib.sha256(config).hexdigest(),
            tuple(sorted(drivers)),
            attributes_file,
            frozenset(boundaries),
        )

    def attributes(
        self,
        root: Path,
        patch: Patch,
        git_dir: Path | None = None,
        attributes_file: Path | None = None,
        filters: tuple[str, ...] = (),
    ) -> str:
        route = (f"--git-dir={git_dir}", f"--work-tree={root}") if git_dir else ()
        if attributes_file is not None:
            route += ("-c", f"core.attributesFile={attributes_file}")
        data = b"".join(p.encode("utf-8") + b"\0" for p in patch.paths)
        raw = (
            self.git.run(root, *route, "check-attr", "--all", "-z", "--stdin", data=data)
            .require()
            .stdout
        )
        fields = raw.split(b"\0")[:-1]
        if len(fields) % 3:
            raise PatchError("Git returned an invalid attribute inventory.")
        rows = sorted(tuple(fields[i : i + 3]) for i in range(0, len(fields), 3))
        for path, name, value in rows:
            if name == b"filter" and (
                value not in (b"unspecified", b"unset")
                or value.decode("utf-8", "replace") in filters
            ):
                raise PatchError(
                    "External Git filters require manual handling (including Git LFS): "
                    + path.decode("utf-8", "replace")
                )
        return hashlib.sha256(b"\0".join(part for row in rows for part in row)).hexdigest()

    def validate_inventory(self, patch: Patch, root: Path) -> None:
        result = self.git.apply(root, patch.data, "--numstat", "-z").require()
        entries = [r for r in result.stdout.split(b"\0") if r]
        if len(entries) != len(patch.files):
            raise PatchError("Git and the review parser disagree about the file inventory.")
        for item, change in zip(entries, patch.files, strict=True):
            pieces = item.split(b"\t", 2)
            if len(pieces) != 3:
                raise PatchError("Unsupported Git patch inventory.")
            add, remove, path = pieces
            if path.decode("utf-8", "strict") != change.path:
                raise PatchError("Git and the review parser disagree about a filename.")
            if change.binary:
                valid = add == remove == b"-"
            else:
                valid = add == str(change.added).encode() and remove == str(change.removed).encode()
            if not valid:
                raise PatchError(
                    "Git and the review parser disagree about the changes. Export a single cumulative Git diff."
                )

    def checks(self, root: Path, patch: Patch, filters: tuple[str, ...] = ()) -> tuple[str, str]:
        forward = self.git.apply(root, patch.data, "--check", filters=filters)
        reverse = self.git.apply(root, patch.data, "--reverse", "--check", filters=filters)
        for result in (forward, reverse):
            if result.code not in (0, 1):
                result.require()
        if forward.code == 0 and reverse.code == 1:
            return "ready", forward.detail
        if forward.code == 0 and reverse.code == 0:
            return (
                "ambiguous",
                "Patch applies in both directions. Context is ambiguous; manual Git review is required.",
            )
        if reverse.code == 0:
            return "applied", "Patch appears already applied (reverse check succeeds)."
        return "conflict", forward.detail or "The patch does not apply to these files."

    def probe(self, folder: Path, patch: Patch) -> Candidate:
        try:
            repo = self.repo_state(folder)
            validate_boundaries(repo, patch.paths)
            self.validate_inventory(patch, repo.root)
            score = 0
            for p in patch.paths:
                if _safe_target(repo.root, p).exists():
                    score += 1
            self.attributes(repo.root, patch, filters=repo.filter_drivers)
            status, reason = self.checks(repo.root, patch, repo.filter_drivers)
            return Candidate(repo.root, status, reason, score, repo.branch_label)
        except (PatchError, OSError, UnicodeError) as exc:
            return Candidate(folder, "blocked", str(exc), -1)

    def detect(
        self, folders: list[str], patch: Patch, cancel: threading.Event | None = None
    ) -> tuple[Candidate, ...]:
        unique = list(dict.fromkeys(path_key(f) for f in folders))[:50]
        result = []
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="repo-check") as pool:
            jobs = {pool.submit(self.probe, Path(f), patch): f for f in unique}
            for future in as_completed(jobs):
                if cancel and cancel.is_set():
                    for job in jobs:
                        job.cancel()
                    break
                result.append(future.result())
        return tuple(sorted(result, key=lambda c: (c.status != "ready", -c.score, str(c.root))))

    def review(self, folder: Path, patch: Patch) -> Review:
        repo = self.repo_state(folder)
        validate_boundaries(repo, patch.paths)
        self.validate_inventory(patch, repo.root)
        paths = patch.paths
        touched = set(paths)
        before = snapshot(repo.root, paths)
        support_paths = tuple(p for p in attribute_paths(paths) if p not in touched)
        validate_boundaries(repo, support_paths)
        support = snapshot(repo.root, support_paths)
        attributes = self.attributes(repo.root, patch, filters=repo.filter_drivers)
        status, diagnostics = self.checks(repo.root, patch, repo.filter_drivers)
        if status != "ready":
            raise PatchError(diagnostics)
        with tempfile.TemporaryDirectory(prefix="patch-to-repo-preview-") as directory:
            sandbox = Path(directory).resolve()
            for file in (*before, *support):
                if file.content is not None:
                    target = sandbox / file.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(file.content)
                    target.chmod(file.mode)
            # use the original read-only Git context with an explicitly isolated work tree
            # this preserves Git's attributes, encoding, ident and EOL semantics
            trial = self.git.apply(
                sandbox,
                patch.data,
                sandbox=True,
                git_dir=repo.git_dir,
                filters=repo.filter_drivers,
                attributes_file=repo.attributes_file,
            )
            if trial.code:
                raise PatchError(
                    "Could not build an isolated preview. No repository files changed.\n"
                    + trial.detail
                )
            self.attributes(sandbox, patch, repo.git_dir, repo.attributes_file, repo.filter_drivers)
            after = snapshot(sandbox, patch.paths)
        if (
            self.repo_state(repo.root) != repo
            or snapshot(repo.root, patch.paths) != before
            or snapshot(repo.root, support_paths) != support
            or self.attributes(repo.root, patch, filters=repo.filter_drivers) != attributes
        ):
            raise PatchError("Repository changed during preview. Run Check again.")
        if before == after:
            raise PatchError("The patch produces no working-file changes.")
        return Review(patch, repo, before, after, diagnostics, attributes)

    def _backup(self, review: Review) -> Path:
        folder = self.data_dir / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"{timestamp}-{uuid.uuid4().hex[:12]}.zip"
        manifest = {
            "schema": 1,
            "repo": str(review.repo.root),
            "patch": review.patch.name,
            "patch_sha256": review.patch.digest,
            "created_utc": timestamp,
            "files": [
                {
                    "path": b.path,
                    "before_sha256": b.digest,
                    "before_mode": b.mode,
                    "after_sha256": a.digest,
                    "after_mode": a.mode,
                    "backup_entry": f"before/{i:06d}.bin" if b.content is not None else None,
                }
                for i, (b, a) in enumerate(zip(review.before, review.after, strict=True))
            ],
        }
        with path.open("xb") as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
            ) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2))
                archive.writestr("reviewed.patch", review.patch.data)
                for i, file in enumerate(review.before):
                    if file.content is not None:
                        archive.writestr(f"before/{i:06d}.bin", file.content)
            stream.flush()
            os.fsync(stream.fileno())
        return path

    def apply(self, review: Review) -> Applied:
        with repository_lock(self.data_dir, review.repo.root):
            fresh = self.review(review.repo.root, review.patch)
            if (
                fresh.repo != review.repo
                or fresh.before != review.before
                or fresh.after != review.after
                or fresh.attribute_digest != review.attribute_digest
            ):
                raise ApplyError(
                    "The repository changed since review. Run Check and review the new result."
                )
            try:
                backup = self._backup(review)
            except OSError as exc:
                raise ApplyError(
                    f"Could not save recovery files. Nothing was applied: {exc}"
                ) from exc
            # backup compression takes time; check again immediately before writing
            try:
                changed = (
                    self.repo_state(review.repo.root) != review.repo
                    or snapshot(review.repo.root, review.patch.paths) != review.before
                    or self.attributes(
                        review.repo.root, review.patch, filters=review.repo.filter_drivers
                    )
                    != review.attribute_digest
                )
            except (OSError, PatchError) as exc:
                raise ApplyError(
                    f"Pre-apply validation failed. Nothing was applied: {exc}", backup
                ) from exc
            if changed:
                raise ApplyError(
                    "Repository changed while preparing recovery data. Nothing was applied; run Check again.",
                    backup,
                )
            try:
                result = self.git.apply(
                    review.repo.root,
                    review.patch.data,
                    "--verbose",
                    filters=review.repo.filter_drivers,
                )
                if result.code:
                    raise ApplyError(
                        "Git could not finish applying. Inspect working files and the recovery bundle before retrying.\n"
                        + result.detail,
                        backup,
                    )
                actual = snapshot(review.repo.root, review.patch.paths)
                after_repo = self.repo_state(review.repo.root)
                verified = actual == review.after and after_repo == review.repo
                detail = result.detail
                if not verified:
                    detail += "\nGit reported success, but the final files or repository state differ from the preview. Inspect the repository and recovery bundle."
                return Applied(backup, detail, verified)
            except ApplyError:
                raise
            except (OSError, PatchError) as exc:
                raise ApplyError(f"Apply status needs inspection: {exc}", backup) from exc
