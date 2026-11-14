from conftest import run
from PySide6.QtCore import Qt

from patchtorepo.storage import Store
from patchtorepo.window import MainWindow


def make_window(qtbot, tmp_path, repo, patch, more=()):
    store = Store(tmp_path / "prefs")
    store.remember(repo)
    for folder in more:
        store.remember(folder)
    path = tmp_path / "sample.patch"
    path.write_bytes(patch.data)
    window = MainWindow(store, str(path))
    qtbot.addWidget(window)
    window.show()
    return window


def ready(qtbot, window):
    qtbot.waitUntil(
        lambda: (
            window._job is None and window.review is not None and bool(window.diff.rendered.left)
        ),
        timeout=10000,
    )


def test_full_review_and_apply_flow(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    assert window.repos.currentData() == str(repo)
    assert not window.apply_button.isEnabled()
    assert window.diff.left.isReadOnly()
    assert "return 1" in window.diff.left.toPlainText()
    assert "return 2" in window.diff.right.toPlainText()
    assert any(line.syntax for line in window.diff.rendered.right)
    qtbot.mouseClick(window.ack, Qt.MouseButton.LeftButton)
    assert window.apply_button.isEnabled()
    qtbot.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._job is None and window._applied, timeout=10000)
    assert not window.apply_button.isEnabled()
    assert "applied and verified" in window.status_label.text()
    assert b"return 2" in (repo / "hello.cpp").read_bytes()


def test_draft_edit_invalidates_review_and_rechecks(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.ack.setChecked(True)
    window.tabs.setCurrentIndex(1)
    window._edit_draft()
    assert not window.source.isReadOnly()
    window.source.setPlainText(window.source.toPlainText().replace("return 2", "return 3"))
    assert window._draft_dirty
    assert not window.apply_button.isEnabled()
    assert not window.ack.isChecked()
    window._use_draft()
    ready(qtbot, window)
    assert "return 3" in window.diff.right.toPlainText()
    assert not window.ack.isChecked()
    assert b"return 2" in (tmp_path / "sample.patch").read_bytes()


def test_multiple_compatible_repos_require_choice(qtbot, tmp_path, repo, patch):
    other = tmp_path / "clone"
    run(repo, "clone", "-q", str(repo), str(other))
    run(other, "config", "core.autocrlf", "false")
    (other / "hello.cpp").unlink()
    run(other, "checkout", "--", "hello.cpp")
    window = make_window(qtbot, tmp_path, repo, patch, (other,))
    qtbot.waitUntil(
        lambda: window._job is None and "2 repositories match" in window.status_label.text(),
        timeout=10000,
    )
    assert window.repos.currentIndex() == -1
    assert not window.apply_button.isEnabled()
    window.repos.setCurrentIndex(window.repos.findData(str(repo)))
    ready(qtbot, window)


def test_new_explorer_request_does_not_replace_review(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    active = window.patch
    window.enqueue(str(tmp_path / "another.patch"))
    assert window.patch is active
    assert len(window._queue) == 1
    assert window.next_patch.isVisible()


def test_recheck_failed_after_file_edit_clears_apply(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.ack.setChecked(True)
    (repo / "hello.cpp").write_text("incompatible\n")
    window.check()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.review is None
    assert not window.apply_button.isEnabled()


def test_longer_diff_pane_can_scroll_past_shorter_pane(qtbot):
    from patchtorepo.diff import Line, Rendered
    from patchtorepo.widgets import DiffView

    view = DiffView()
    qtbot.addWidget(view)
    view.resize(700, 400)
    view.show()
    view.show_render(Rendered((Line("short", 1),), (Line("x" * 300, 1),), (), ""))
    qtbot.waitUntil(lambda: view.right.horizontalScrollBar().maximum() > 100)
    bar = view.right.horizontalScrollBar()
    bar.setValue(bar.maximum())
    assert bar.value() == bar.maximum()
    assert view.left.horizontalScrollBar().value() == 0


def test_patch_still_opens_when_git_is_missing(qtbot, tmp_path, patch, monkeypatch):
    from patchtorepo import window as module
    from patchtorepo.git import GitError

    def missing(*_):
        raise GitError("Git is missing")

    monkeypatch.setattr(module, "Git", missing)
    path = tmp_path / "open-even-without-git.patch"
    path.write_bytes(patch.data)
    widget = MainWindow(Store(tmp_path / "preferences"), str(path))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitUntil(lambda: widget._job is None and widget.patch is not None, timeout=10000)
    assert widget.patch.data == patch.data
    assert not widget.apply_button.isEnabled()
    assert "Locate Git" in widget.status_label.text()
