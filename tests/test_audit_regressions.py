import pytest
from conftest import run
from PySide6.QtWidgets import QMessageBox
from test_ui import make_window, ready

from patchtorepo.diff import render
from patchtorepo.engine import ApplyError, FileState
from patchtorepo.patch import Patch, PatchError

ADDITION = (
    b"diff --git a/new.txt b/new.txt\nnew file mode 100644\n"
    b"--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+first\n+last\n"
)


@pytest.mark.parametrize("source", ["attributes", "config"])
def test_preview_matches_repository_line_endings(engine, repo, source):
    if source == "attributes":
        (repo / ".gitattributes").write_text("*.txt text eol=crlf\n")
    else:
        run(repo, "config", "core.autocrlf", "true")
    review = engine.review(repo, Patch.parse(ADDITION))
    assert review.pair(0)[1].content == b"first\r\nlast\r\n"
    assert engine.apply(review).verified


def test_failed_queued_open_keeps_draft_guard(qtbot, tmp_path, repo, patch, monkeypatch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window._edit_draft()
    edited = window.source.toPlainText().replace("return 2", "return 3")
    window.source.setPlainText(edited)
    window.enqueue(str(tmp_path / "missing.patch"))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window._open_next()
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.source.toPlainText() == edited
    assert window._draft_dirty
    assert not window.ack.isEnabled()
    assert not window.apply_button.isEnabled()


def test_open_larger_patch_with_active_filter(qtbot, tmp_path, repo, patch, monkeypatch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.file_filter.setText("hello")
    monkeypatch.setattr(window, "detect", lambda: None)
    with qtbot.captureExceptions() as errors:
        window._loaded(Patch.parse(patch.data + ADDITION))
    assert not errors
    assert window.files.topLevelItemCount() == 2
    assert not window.file_filter.text()
    assert all(not window.files.topLevelItem(i).isHidden() for i in range(2))


@pytest.mark.parametrize("control", ["\x0c", "\u2028", "\u2029", "\x85"])
def test_unicode_separators_keep_review_line_numbers(control):
    before = FileState("x.py", f"# first{control}still first\nvalue = 1\n".encode())
    after = FileState("x.py", f"# first{control}still first\nvalue = 2\n".encode())
    result = render(before, after, "x.py")
    assert [line.number for line in result.left] == [1, 2]
    assert [line.number for line in result.right] == [1, 2]
    assert result.changes == (1,)


def test_find_deleted_code_after_focusing_search(qtbot, tmp_path, repo, patch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.diff.left.setFocus()
    window.find_text.setText("return 1")
    window.find_text.setFocus()
    window._find()
    assert window.diff.left.textCursor().selectedText() == "return 1"


@pytest.mark.parametrize("location", ["nested", "info", "global", "relative", "index"])
def test_attribute_precedence_and_index_fallback(engine, repo, tmp_path, location):
    (repo / "nested").mkdir()
    raw = ADDITION.replace(b"a/new.txt", b"a/nested/new.txt").replace(
        b"b/new.txt", b"b/nested/new.txt"
    )
    attributes = "*.txt text eol=crlf\n"
    if location == "nested":
        (repo / ".gitattributes").write_text("*.txt text eol=lf\n")
        (repo / "nested/.gitattributes").write_text(attributes)
    elif location == "info":
        (repo / ".gitattributes").write_text("*.txt text eol=lf\n")
        (repo / ".git/info/attributes").write_text(attributes)
    elif location == "global":
        path = tmp_path / "global.attributes"
        path.write_text(attributes)
        run(repo, "config", "core.attributesFile", str(path))
    elif location == "relative":
        (repo / "custom.attributes").write_text(attributes)
        run(repo, "config", "core.attributesFile", "custom.attributes")
    else:
        path = repo / ".gitattributes"
        path.write_text(attributes)
        run(repo, "add", ".gitattributes")
        path.unlink()
    index = (repo / ".git/index").read_bytes()
    review = engine.review(repo, Patch.parse(raw))
    assert not (repo / "nested/new.txt").exists()
    assert (repo / ".git/index").read_bytes() == index
    # plain working-tree apply does not load the index for attribute fallback
    expected = b"first\nlast\n" if location == "index" else b"first\r\nlast\r\n"
    assert review.pair(0)[1].content == expected
    assert engine.apply(review).verified
    assert (repo / ".git/index").read_bytes() == index


@pytest.mark.parametrize("attribute", ["text eol=crlf", "text working-tree-encoding=UTF-16"])
def test_patch_can_add_attributes_and_data_together(engine, repo, attribute):
    # the same Git context and operation order must be used by preview and Apply
    raw = (
        b"diff --git a/.gitattributes b/.gitattributes\nnew file mode 100644\n"
        b"--- /dev/null\n+++ b/.gitattributes\n@@ -0,0 +1 @@\n+*.txt "
        + attribute.encode()
        + b"\n"
        + ADDITION
    )
    review = engine.review(repo, Patch.parse(raw))
    assert not (repo / ".gitattributes").exists()
    # Git caches the attributes before writing this patch's new attributes file
    assert review.pair(1)[1].content == b"first\nlast\n"
    assert engine.apply(review).verified


@pytest.mark.parametrize("encoding", ["crlf", "utf16"])
def test_existing_converted_file_has_exact_preview(engine, repo, patch, encoding):
    attribute = "text eol=crlf" if encoding == "crlf" else "text working-tree-encoding=UTF-16"
    (repo / ".gitattributes").write_text(f"*.cpp {attribute}\n")
    original = "int main() {\n    return 1;\n}\n"
    expected = original.replace("return 1", "return 2")
    if encoding == "crlf":
        before, after = (text.replace("\n", "\r\n").encode() for text in (original, expected))
    else:
        before, after = (text.encode("utf-16") for text in (original, expected))
    (repo / "hello.cpp").write_bytes(before)
    review = engine.review(repo, patch)
    assert review.pair(0)[1].content == after
    assert (repo / "hello.cpp").read_bytes() == before
    assert engine.apply(review).verified


def test_ident_expansion_is_in_actual_preview(engine, repo):
    (repo / ".gitattributes").write_text("*.txt ident\n")
    review = engine.review(repo, Patch.parse(ADDITION.replace(b"+first", b"+$Id$")))
    assert review.pair(0)[1].content.startswith(b"$Id: ")
    assert engine.apply(review).verified


@pytest.mark.parametrize("introduced", [False, True])
@pytest.mark.parametrize("driver", ["audit", "unset", "unspecified"])
def test_external_filters_are_refused_without_execution(engine, repo, tmp_path, introduced, driver):
    import shlex
    import sys

    marker = tmp_path / "filter-ran"
    script = tmp_path / "filter.py"
    script.write_text(
        "from pathlib import Path\nimport sys\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    )
    command = shlex.quote(sys.executable.replace("\\", "/")) + " " + shlex.quote(script.as_posix())
    for key in ("clean", "smudge"):
        run(repo, "config", f"filter.{driver}.{key}", command)
    run(repo, "config", f"filter.{driver}.required", "true")
    raw = ADDITION
    if introduced:
        raw = (
            b"diff --git a/.gitattributes b/.gitattributes\nnew file mode 100644\n"
            b"--- /dev/null\n+++ b/.gitattributes\n@@ -0,0 +1 @@\n+*.txt filter="
            + driver.encode()
            + b"\n"
            + raw
        )
    else:
        (repo / ".gitattributes").write_text(f"*.txt filter={driver}\n")
    with pytest.raises(PatchError, match="External Git filters"):
        engine.review(repo, Patch.parse(raw))
    assert not marker.exists()
    assert not (repo / "new.txt").exists()


@pytest.mark.parametrize("change", ["config", "attributes"])
def test_changed_conversion_context_blocks_stale_review(engine, repo, change):
    review = engine.review(repo, Patch.parse(ADDITION))
    if change == "config":
        run(repo, "config", "core.autocrlf", "true")
    else:
        (repo / ".git/info/attributes").write_text("*.txt text eol=crlf\n")
    with pytest.raises(ApplyError, match="changed since review"):
        engine.apply(review)
    assert not (repo / "new.txt").exists()


def test_attributes_changed_during_backup_block_write(engine, repo, monkeypatch):
    review = engine.review(repo, Patch.parse(ADDITION))
    backup = engine._backup

    def race(review):
        path = backup(review)
        (repo / ".git/info/attributes").write_text("*.txt text eol=crlf\n")
        return path

    monkeypatch.setattr(engine, "_backup", race)
    with pytest.raises(ApplyError, match="changed while preparing") as caught:
        engine.apply(review)
    assert caught.value.backup.is_file()
    assert not (repo / "new.txt").exists()


def test_unicode_controls_have_visible_labels_in_qt(qtbot):
    from patchtorepo.widgets import DiffView

    view = DiffView()
    qtbot.addWidget(view)
    content = "# a\u2029b\u2028c\x0cd\u202ee\u00a0f\nvalue = 1\n".encode()
    result = render(
        FileState("x.py", content), FileState("x.py", content.replace(b"= 1", b"= 2")), "x.py"
    )
    view.show_render(result)
    assert view.left.document().blockCount() == 2
    assert "⟦U+2029⟧" in view.left.toPlainText()
    assert "⟦U+202E⟧" in view.left.toPlainText()
    assert "Control/format" in view.note.text()
    assert all(line.number == i + 1 for i, line in enumerate(view.left.lines))


def test_utf16_metadata_reports_real_line_endings():
    state = FileState("x.txt", "first\r\nlast\r\n".encode("utf-16"))
    result = render(state, state, "x.txt")
    assert "UTF-16 · CRLF" in result.note
    assert "no final newline" not in result.note


def test_unrepresentable_patch_source_is_read_only(qtbot, tmp_path, repo, patch, monkeypatch):
    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    monkeypatch.setattr(window, "detect", lambda: None)
    raw = patch.data.replace(b"+    return 2;", "+    return 2; // a\u2029b".encode())
    window._loaded(Patch.parse(raw))
    assert not window._draft_editable
    assert window.source.isReadOnly()
    assert "⟦U+2029⟧" in window.source.toPlainText()
    assert window.patch.data == raw


def test_render_failure_clears_stale_code_and_apply(qtbot, tmp_path, repo, patch, monkeypatch):
    from patchtorepo import window as module

    window = make_window(qtbot, tmp_path, repo, patch)
    ready(qtbot, window)
    window.ack.setChecked(True)

    def fail(*args):
        raise ValueError("simulated rendering failure")

    monkeypatch.setattr(module, "render", fail)
    window._render_cache.clear()
    window._file_changed(window.files.currentItem(), None)
    qtbot.waitUntil(lambda: window._job is None, timeout=10000)
    assert window.review is None
    assert not window.apply_button.isEnabled()
    assert not window.diff.right.toPlainText()
