import json
import zipfile

import pytest
from conftest import run

from patchtorepo.engine import ApplyError
from patchtorepo.patch import Patch, PatchError
from patchtorepo.storage import repository_lock


def test_preview_and_apply_preserve_index_history_and_local_edits(engine, repo, patch):
    (repo / "other.txt").write_text("unrelated local work")
    index = (repo / ".git/index").read_bytes()
    head = run(repo, "rev-parse", "HEAD")
    review = engine.review(repo, patch)
    assert b"return 1" in (repo / "hello.cpp").read_bytes()
    assert b"return 2" in review.pair(0)[1].content
    outcome = engine.apply(review)
    assert outcome.verified
    assert b"return 2" in (repo / "hello.cpp").read_bytes()
    assert (repo / ".git/index").read_bytes() == index
    assert run(repo, "rev-parse", "HEAD") == head
    assert (repo / "other.txt").read_text() == "unrelated local work"
    with zipfile.ZipFile(outcome.backup) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.read(manifest["files"][0]["backup_entry"]) == review.before[0].content
        assert archive.read("reviewed.patch") == patch.data
    with pytest.raises(PatchError, match="already applied"):
        engine.review(repo, patch)


def test_stale_review_cannot_apply_even_when_context_still_matches(engine, repo, patch):
    review = engine.review(repo, patch)
    (repo / "hello.cpp").write_bytes(review.before[0].content + b"// external edit\n")
    with pytest.raises(ApplyError, match="changed since review"):
        engine.apply(review)
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_index_change_invalidates_review(engine, repo, patch):
    review = engine.review(repo, patch)
    (repo / "other.txt").write_text("stage elsewhere")
    run(repo, "add", "other.txt")
    with pytest.raises(ApplyError, match="changed since review"):
        engine.apply(review)


def test_changed_source_patch_does_not_change_snapshot(engine, repo, patch, tmp_path):
    path = tmp_path / "download.patch"
    path.write_bytes(patch.data)
    loaded = Patch.read(path)
    review = engine.review(repo, loaded)
    path.write_bytes(patch.data.replace(b"return 2", b"return 9"))
    assert engine.apply(review).verified
    assert b"return 2" in (repo / "hello.cpp").read_bytes()


def test_conflict_leaves_every_file_untouched(engine, repo, patch):
    original = (repo / "hello.cpp").read_bytes().replace(b"return 1", b"return 99")
    (repo / "hello.cpp").write_bytes(original)
    with pytest.raises(PatchError):
        engine.review(repo, patch)
    assert (repo / "hello.cpp").read_bytes() == original


def test_added_deleted_renamed_binary_and_unicode(engine, repo):
    (repo / "delete.txt").write_bytes(b"gone\n")
    (repo / "rename old.txt").write_bytes(b"rename this file\n" * 20)
    (repo / "blob.bin").write_bytes(bytes(range(256)) * 20)
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "fixtures")
    (repo / "delete.txt").unlink()
    run(repo, "mv", "rename old.txt", "rename new.txt")
    (repo / "blob.bin").write_bytes(b"\0\1new" * 30)
    (repo / "日本語 new.txt").write_bytes(b"new file\n")
    run(repo, "add", ".")
    raw = run(repo, "diff", "--cached", "--binary", "--full-index")
    run(repo, "reset", "--hard", "HEAD")
    patch = Patch.parse(raw)
    review = engine.review(repo, patch)
    assert engine.apply(review).verified
    assert not (repo / "delete.txt").exists()
    assert not (repo / "rename old.txt").exists()
    assert (repo / "rename new.txt").exists()
    assert (repo / "日本語 new.txt").read_bytes() == b"new file\n"


@pytest.mark.parametrize("body", [b"one\r\ntwo\r\n", b"one\ntwo", b"caf\xe9\nold\n"])
def test_line_endings_missing_final_newline_and_legacy_bytes(engine, repo, body):
    (repo / "bytes.txt").write_bytes(body)
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "bytes")
    expected = body.replace(b"two", b"three").replace(b"old", b"new")
    (repo / "bytes.txt").write_bytes(expected)
    raw = run(repo, "diff", "--binary")
    run(repo, "checkout", "--", "bytes.txt")
    assert engine.apply(engine.review(repo, Patch.parse(raw))).verified
    assert (repo / "bytes.txt").read_bytes() == expected


def test_readonly_file_retains_checked_behavior(engine, repo, patch):
    # Git's file-mode handling differs on Windows; preview and real apply must agree
    (repo / "hello.cpp").chmod(0o444)
    try:
        review = engine.review(repo, patch)
        assert engine.apply(review).verified
    finally:
        (repo / "hello.cpp").chmod(0o644)


def test_forward_reverse_ambiguity_is_blocked(engine, repo):
    (repo / "repeat.txt").write_bytes(b"intro\nbefore\nold\nafter\n\nbefore\nnew\nafter\n")
    raw = b"diff --git a/repeat.txt b/repeat.txt\n--- a/repeat.txt\n+++ b/repeat.txt\n@@ -2,3 +2,3 @@\n before\n-old\n+new\n after\n"
    with pytest.raises(PatchError, match="both directions"):
        engine.review(repo, Patch.parse(raw))


def test_unsafe_repository_parent_symlink_is_blocked(engine, repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (repo / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    patch = Patch.parse(
        b"diff --git a/linked/new.txt b/linked/new.txt\nnew file mode 100644\n--- /dev/null\n+++ b/linked/new.txt\n@@ -0,0 +1 @@\n+new\n"
    )
    with pytest.raises(PatchError, match="Symlink|junction"):
        engine.review(repo, patch)
    assert not (outside / "new.txt").exists()


def test_detect_unique_and_ambiguous_matches(engine, repo, patch, tmp_path):
    other = tmp_path / "other"
    run(repo, "clone", "-q", str(repo), str(other))
    run(other, "config", "core.autocrlf", "false")
    (other / "hello.cpp").unlink()
    run(other, "checkout", "--", "hello.cpp")
    choices = engine.detect([str(repo), str(other), str(tmp_path / "missing")], patch)
    assert sum(c.status == "ready" for c in choices) == 2
    (other / "hello.cpp").write_bytes(b"wrong\n")
    choices = engine.detect([str(repo), str(other)], patch)
    assert [c.root for c in choices if c.status == "ready"] == [repo]


def test_application_lock_rejects_second_writer(engine, repo, patch):
    review = engine.review(repo, patch)
    with repository_lock(engine.data_dir, repo):
        with pytest.raises(PatchError, match="Another Patch"):
            engine.apply(review)


def test_backup_failure_prevents_write(engine, repo, patch, monkeypatch):
    review = engine.review(repo, patch)

    def fail(_):
        raise OSError("full disk")

    monkeypatch.setattr(engine, "_backup", fail)
    with pytest.raises(ApplyError, match="Nothing was applied"):
        engine.apply(review)
    assert (repo / "hello.cpp").read_bytes() == review.before[0].content


def test_linked_worktree(engine, repo, patch, tmp_path):
    other = tmp_path / "linked worktree"
    run(repo, "worktree", "add", "-q", "-b", "test-linked", str(other))
    review = engine.review(other, patch)
    assert review.repo.root == other
    assert engine.apply(review).verified
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_override_environment_and_whitespace_config(engine, repo, patch, monkeypatch):
    monkeypatch.setenv("GIT_WORK_TREE", "/invalid")
    monkeypatch.setenv("GIT_INDEX_FILE", "/invalid/index")
    run(repo, "config", "apply.whitespace", "fix")
    edited = Patch.parse(patch.data.replace(b"+    return 2;", b"+    return 2;  "))
    assert engine.apply(engine.review(repo, edited)).verified
    assert b"return 2;  \n" in (repo / "hello.cpp").read_bytes()


def test_local_edits_in_affected_file_are_preserved(engine, repo, patch):
    (repo / "hello.cpp").write_bytes((repo / "hello.cpp").read_bytes() + b"// local addition\n")
    review = engine.review(repo, patch)
    assert b"// local addition" in review.pair(0)[1].content
    assert engine.apply(review).verified
    assert b"// local addition" in (repo / "hello.cpp").read_bytes()


def test_unmerged_index_blocks_patch(engine, repo, patch):
    run(repo, "checkout", "-qb", "feature")
    (repo / "hello.cpp").write_bytes(b"feature\n")
    run(repo, "commit", "-qam", "feature")
    run(repo, "checkout", "-q", "-")
    (repo / "hello.cpp").write_bytes(b"main\n")
    run(repo, "commit", "-qam", "main")
    import subprocess

    subprocess.run(["git", "-C", str(repo), "merge", "feature"], capture_output=True)
    with pytest.raises(PatchError, match="unresolved"):
        engine.review(repo, patch)


def test_empty_file_addition(engine, repo):
    raw = b"diff --git a/empty.txt b/empty.txt\nnew file mode 100644\nindex 0000000..e69de29\n"
    assert engine.apply(engine.review(repo, Patch.parse(raw))).verified
    assert (repo / "empty.txt").read_bytes() == b""


def test_copy_patch_preserves_source(engine, repo):
    raw = b"diff --git a/hello.cpp b/copy.cpp\nsimilarity index 100%\ncopy from hello.cpp\ncopy to copy.cpp\n"
    review = engine.review(repo, Patch.parse(raw))
    assert engine.apply(review).verified
    assert (repo / "copy.cpp").read_bytes() == (repo / "hello.cpp").read_bytes()


def test_failed_apply_keeps_recovery_bundle_and_does_not_claim_success(
    engine, repo, patch, monkeypatch
):
    from patchtorepo.git import Result

    review = engine.review(repo, patch)
    original = engine.git.apply

    def fail_apply(root, data, *options, **kwargs):
        if root == repo and "--verbose" in options:
            return Result(1, b"", b"simulated write failure")
        return original(root, data, *options, **kwargs)

    monkeypatch.setattr(engine.git, "apply", fail_apply)
    with pytest.raises(ApplyError) as caught:
        engine.apply(review)
    assert caught.value.backup.is_file()
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_post_apply_mismatch_is_reported(engine, repo, patch, monkeypatch):
    review = engine.review(repo, patch)
    original = engine.git.apply

    def race(root, data, *options, **kwargs):
        result = original(root, data, *options, **kwargs)
        if root == repo and "--verbose" in options:
            (repo / "hello.cpp").write_bytes(b"external writer after Git\n")
        return result

    monkeypatch.setattr(engine.git, "apply", race)
    outcome = engine.apply(review)
    assert not outcome.verified
    assert outcome.backup.is_file()


def test_crlf_checkout_with_autocrlf(engine, repo):
    (repo / "crlf.txt").write_bytes(b"before\nmiddle\nafter\n")
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "line endings")
    (repo / "crlf.txt").write_bytes(b"before\nchanged\nafter\n")
    raw = run(repo, "diff")
    run(repo, "config", "core.autocrlf", "true")
    (repo / "crlf.txt").unlink()
    run(repo, "checkout", "--", "crlf.txt")
    # plain Git apply may refuse LF patches against CRLF worktree bytes; never normalize silently
    try:
        review = engine.review(repo, Patch.parse(raw))
    except PatchError:
        assert (repo / "crlf.txt").read_bytes() == b"before\r\nmiddle\r\nafter\r\n"
    else:
        assert engine.apply(review).verified
