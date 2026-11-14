import gc
import sqlite3

import pytest
from conftest import run
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QSpinBox
from test_ui import make_window, ready

from patchtorepo.patch import Patch, PatchError
from patchtorepo.storage import Store


def test_adding_repo_during_draft_edit_cannot_keep_previous_target(
    qtbot, tmp_path, repo, patch, monkeypatch
):
    other = tmp_path / "second repository"
    run(repo, "clone", "-q", str(repo), str(other))
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window._edit_draft()
    window.source.setPlainText(window.source.toPlainText().replace("return 2", "return 3"))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(other))
    window.add_repo()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.repos.currentData() == str(other)
    window._discard_draft()
    window.ack.setChecked(True)
    assert not window.apply_button.isEnabled()
    assert window.review is None or window.review.repo.root == other
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_valid_removal_that_resembles_email_signature(engine, repo):
    file = repo / "list.md"
    file.write_bytes(b"before\n- \nafter\n")
    run(repo, "add", "list.md")
    run(repo, "commit", "-qm", "text fixture")
    file.write_bytes(b"before\nafter\n")
    patch = Patch.parse(run(repo, "diff"))
    run(repo, "checkout", "--", "list.md")
    assert engine.apply(engine.review(repo, patch)).verified
    assert file.read_bytes() == b"before\nafter\n"


def test_preference_connections_are_closed_before_return(tmp_path, monkeypatch):
    opened = []
    connect = sqlite3.connect

    def track(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", track)
    store = Store(tmp_path / "preferences")
    try:
        store.set("test", "value")
        assert store.get("test") == "value"
        store.remember(tmp_path)
        store.repos()
        store.forget(tmp_path)
        for connection in opened:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        for connection in opened:
            connection.close()
        gc.collect()


def test_patch_cannot_write_into_uninitialized_submodule(engine, repo):
    commit = run(repo, "rev-parse", "HEAD").decode().strip()
    (repo / ".gitmodules").write_text('[submodule "nested"]\n\tpath = nested\n\turl = ./example\n')
    run(repo, "add", ".gitmodules")
    run(repo, "update-index", "--add", "--cacheinfo", f"160000,{commit},nested")
    run(repo, "commit", "-qm", "registered submodule")
    (repo / "nested").mkdir()
    patch = Patch.parse(
        b"diff --git a/nested/new.txt b/nested/new.txt\nnew file mode 100644\n"
        b"--- /dev/null\n+++ b/nested/new.txt\n@@ -0,0 +1 @@\n+new\n"
    )
    with pytest.raises(PatchError, match="[Ss]ubmodule|gitlink|[Nn]ested|boundary"):
        engine.review(repo, patch)
    assert not (repo / "nested/new.txt").exists()
    assert not run(repo, "status", "--porcelain")


def test_settings_failure_does_not_report_saved(qtbot, tmp_path, repo, patch, monkeypatch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    previous_review = window.review
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    real_connect = window.store.connect

    def fail():
        raise sqlite3.OperationalError("disk is full")

    def change_settings():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QSpinBox).setValue(18)
        monkeypatch.setattr(window.store, "connect", fail)
        dialog.accept()

    QTimer.singleShot(10, change_settings)
    window.settings()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    monkeypatch.setattr(window.store, "connect", real_connect)
    assert warnings or "disk is full" in window.status_label.text()
    assert "Settings saved" not in window.status_label.text()
    assert window.review is previous_review
    assert window.diff.left.font().pointSize() == 11


@pytest.mark.parametrize("shortcut", [False, True])
def test_apply_handler_rejects_mismatched_selector_even_without_signal(
    qtbot, tmp_path, repo, patch, shortcut
):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.ack.setChecked(True)
    # exercise the final action guard independently of the selector's signals
    window.repos.blockSignals(True)
    window.repos.setItemData(window.repos.currentIndex(), str(tmp_path / "wrong destination"))
    window.repos.blockSignals(False)
    if shortcut:
        qtbot.keyClick(window, Qt.Key.Key_Return, modifier=Qt.KeyboardModifier.ControlModifier)
    else:
        window.apply()
    assert window._job is None
    assert window.review is None
    assert not window.apply_button.isEnabled()
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_recheck_after_draft_repo_switch_applies_only_selected_repo(
    qtbot, tmp_path, repo, patch, monkeypatch
):
    other = tmp_path / "other"
    run(repo, "clone", "-q", str(repo), str(other))
    run(other, "config", "core.autocrlf", "false")
    (other / "hello.cpp").unlink()
    run(other, "checkout", "--", "hello.cpp")
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window._edit_draft()
    window.source.setPlainText(window.source.toPlainText().replace("return 2", "return 3"))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(other))
    window.add_repo()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert not window.diff.left.toPlainText()
    window._discard_draft()
    window.check()
    ready(qtbot, window)
    assert window.review.repo.root == other
    window.ack.setChecked(True)
    window.apply()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window._applied
    assert b"return 2" in (other / "hello.cpp").read_bytes()
    assert b"return 1" in (repo / "hello.cpp").read_bytes()


def test_subdirectory_history_entry_binds_to_reviewed_root(qtbot, tmp_path, repo, patch):
    subfolder = repo / "subfolder"
    subfolder.mkdir()
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.repos.setItemData(window.repos.currentIndex(), str(subfolder))
    window.check()
    ready(qtbot, window)
    assert window.repos.currentData() == str(repo)
    window.ack.setChecked(True)
    assert window.apply_button.isEnabled()


def test_normal_repo_switch_clears_draft_review(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window._edit_draft()
    window.source.setPlainText(window.source.toPlainText() + "\n")
    window.repos.addItem("different repo", str(tmp_path / "different"))
    window.repos.setCurrentIndex(window.repos.count() - 1)
    assert window.review is None
    assert not window.diff.left.toPlainText()
    assert window._draft_dirty
    window._discard_draft()
    assert not window.ack.isEnabled()


@pytest.mark.parametrize("mode", ["120000", "160000"])
@pytest.mark.parametrize("path", ["nested", "日本語[1]"])
def test_index_boundaries_block_missing_or_replaced_worktree_entries(engine, repo, mode, path):
    oid = run(repo, "rev-parse", "HEAD" if mode == "160000" else "HEAD:hello.cpp").decode().strip()
    run(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")
    raw = (
        f"diff --git a/{path}/new.txt b/{path}/new.txt\nnew file mode 100644\n"
        f"--- /dev/null\n+++ b/{path}/new.txt\n@@ -0,0 +1 @@\n+new\n"
    ).encode()
    patch = Patch.parse(raw)
    for create_directory in (False, True):
        if create_directory:
            (repo / path).mkdir()
        with pytest.raises(PatchError, match="boundary"):
            engine.review(repo, patch)
        assert engine.probe(repo, patch).status == "blocked"
        assert not (repo / path / "new.txt").exists()


def test_unrelated_submodule_does_not_block_ordinary_files(engine, repo, patch):
    oid = run(repo, "rev-parse", "HEAD").decode().strip()
    run(repo, "update-index", "--add", "--cacheinfo", f"160000,{oid},untouched")
    assert engine.apply(engine.review(repo, patch)).verified


def test_linked_worktree_uses_its_own_index_boundaries(engine, repo, patch, tmp_path):
    other = tmp_path / "linked"
    run(repo, "worktree", "add", "-q", "-b", "linked-audit", str(other))
    oid = run(repo, "rev-parse", "HEAD").decode().strip()
    run(other, "update-index", "--add", "--cacheinfo", f"160000,{oid},hello.cpp")
    with pytest.raises(PatchError, match="boundary"):
        engine.review(other, patch)
    assert engine.review(repo, patch).repo.root == repo


@pytest.mark.parametrize("body", [b"- \n", b"- \r\n", b"- "])
def test_signature_like_content_with_line_endings_and_eof(engine, repo, body):
    file = repo / "notes.txt"
    file.write_bytes(b"before\n" + body)
    run(repo, "add", "notes.txt")
    run(repo, "commit", "-qm", "content")
    file.write_bytes(b"before\nreplacement\n")
    patch = Patch.parse(run(repo, "diff"))
    run(repo, "checkout", "--", "notes.txt")
    assert patch.files[0].removed == 1
    assert engine.apply(engine.review(repo, patch)).verified


def test_format_patch_signature_is_not_counted_as_hunk_data(engine, repo):
    (repo / "hello.cpp").write_bytes(b"int main() {\n    return 9;\n}\n")
    run(repo, "commit", "-qam", "email patch")
    raw = run(repo, "format-patch", "-1", "--stdout", "--signature=+ Team\n- Contact\n@@ website")
    run(repo, "reset", "--hard", "HEAD^")
    patch = Patch.parse(raw)
    assert patch.files[0].added == patch.files[0].removed == 1
    assert engine.apply(engine.review(repo, patch)).verified


def test_multiple_hunks_include_a_signature_like_deletion(engine, repo):
    file = repo / "multi.txt"
    original = b"start\n- \n" + b"middle\n" * 20 + b"old\nend\n"
    file.write_bytes(original)
    run(repo, "add", "multi.txt")
    run(repo, "commit", "-qm", "multiple")
    file.write_bytes(original.replace(b"- \n", b"updated\n").replace(b"old\n", b"new\n"))
    raw = run(repo, "diff")
    assert raw.count(b"@@ -") == 2
    patch = Patch.parse(raw)
    run(repo, "checkout", "--", "multi.txt")
    assert patch.files[0].added == patch.files[0].removed == 2
    assert engine.apply(engine.review(repo, patch)).verified


@pytest.mark.parametrize("header", [b"@@ -1,2 +1,3 @@", b"@@ -1,4 +1,3 @@", b"@@ invalid @@"])
def test_hunk_count_errors_fail_closed(engine, repo, patch, header):
    original = (repo / "hello.cpp").read_bytes()
    with pytest.raises(PatchError):
        engine.review(repo, Patch.parse(patch.data.replace(b"@@ -1,3 +1,3 @@", header)))
    assert (repo / "hello.cpp").read_bytes() == original


def test_settings_transaction_rolls_back_all_values_and_closes(tmp_path):
    store = Store(tmp_path / "preferences")
    store.set_many({"git": "old-git", "font_size": 11})
    with store.connect() as db:
        db.execute(
            "CREATE TRIGGER fail_font BEFORE INSERT ON settings WHEN NEW.key='font_size' BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
        store.set_many({"git": "new-git", "font_size": 18})
    assert store.get("git") == "old-git"
    assert store.get("font_size") == 11
    with store.connect() as db:
        db.execute("DROP TRIGGER fail_font")
    store.set("after_error", True)
    assert store.get("after_error") is True


def test_failed_transaction_closes_connection(tmp_path, monkeypatch):
    opened = []
    connect = sqlite3.connect

    def track(*args, **kwargs):
        db = connect(*args, **kwargs)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", track)
    store = Store(tmp_path / "preferences")
    with pytest.raises(sqlite3.OperationalError):
        with store.connect() as db:
            db.execute("INSERT INTO nonexistent VALUES (1)")
    for db in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            db.execute("SELECT 1")


def test_settings_commit_updates_ui_only_after_success(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)

    def change_settings():
        dialog = QApplication.activeModalWidget()
        dialog.findChild(QSpinBox).setValue(16)
        dialog.accept()

    QTimer.singleShot(10, change_settings)
    window.settings()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.store.get("font_size") == 16
    assert window.diff.left.font().pointSize() == 16
    assert "Settings saved" in window.status_label.text()
    assert window.review is None
    assert not window.apply_button.isEnabled()


def test_failed_repository_save_keeps_selection_and_error(
    qtbot, tmp_path, repo, patch, monkeypatch
):
    other = tmp_path / "unsaved"
    run(repo, "clone", "-q", str(repo), str(other))
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    previous = window.review

    def fail(*args):
        raise sqlite3.OperationalError("history write failed")

    monkeypatch.setattr(window.store, "remember", fail)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(other))
    window.add_repo()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.repos.currentData() == str(repo)
    assert window.review is previous
    assert "history write failed" in window.status_label.text()
    assert "history write failed" in window.diagnostics.toPlainText()


def test_check_keeps_history_failure_visible_after_render(
    qtbot, tmp_path, repo, patch, monkeypatch
):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)

    def fail(*args):
        raise sqlite3.OperationalError("history write failed")

    monkeypatch.setattr(window.store, "remember", fail)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    window.check()
    ready(qtbot, window)
    assert "history could not be saved" in window.status_label.text()
    assert "history write failed" in window.diagnostics.toPlainText()
    assert window.review.repo.root == repo
