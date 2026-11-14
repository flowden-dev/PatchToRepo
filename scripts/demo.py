"""Render the actual desktop UI against disposable example repositories."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from patchtorepo.storage import Store
from patchtorepo.theme import STYLE
from patchtorepo.window import MainWindow

BEFORE = """from pathlib import Path


def load_notes(path: Path):
    text = path.read_text()
    return text.splitlines()


def clean_notes(notes):
    return [note.strip() for note in notes]


def save_notes(path: Path, notes):
    path.write_text("\\n".join(notes))
"""
AFTER = """from pathlib import Path


def load_notes(path: Path):
    text = path.read_text(encoding="utf-8")
    return text.splitlines()


def clean_notes(notes):
    cleaned = [note.strip() for note in notes]
    return [note for note in cleaned if note]


def save_notes(path: Path, notes):
    content = "\\n".join(notes)
    if content:
        content += "\\n"
    path.write_text(content, encoding="utf-8")
"""


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/screenshot.png")
    output = output.resolve()
    with tempfile.TemporaryDirectory(prefix="patchtorepo-demo-") as temporary:
        folder = Path(temporary)
        repo = folder / "notes-cli"
        repo.mkdir()

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True
            ).stdout

        git("init", "-q", "--initial-branch=main")
        git("config", "commit.gpgSign", "false")
        git("config", "core.autocrlf", "false")
        hooks = folder / "empty-hooks"
        hooks.mkdir()
        git("config", "core.hooksPath", str(hooks))
        git("config", "user.name", "Demo")
        git("config", "user.email", "demo@example.invalid")
        (repo / "src").mkdir()
        (repo / "src/notes.py").write_text(BEFORE, encoding="utf-8")
        (repo / "README.md").write_text("# Notes CLI\n\nA small notes utility.\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "sample")
        (repo / "src/notes.py").write_text(AFTER, encoding="utf-8")
        (repo / "README.md").write_text(
            "# Notes CLI\n\nSave non-empty notes as UTF-8 text.\n", encoding="utf-8"
        )
        patch = folder / "clean-notes.patch"
        patch.write_bytes(git("diff", "--binary"))
        git("checkout", "--", ".")
        app = QApplication([])
        app.setStyle("Fusion")
        app.setFont(QFont("DejaVu Sans", 10))
        app.setStyleSheet(STYLE)
        store = Store(folder / "settings")
        store.remember(repo)
        store.set("font_size", 10)
        window = MainWindow(store, str(patch))
        window.resize(1320, 820)
        window.splitter.setSizes([240, 1080])
        window.show()
        phase = [0]
        captured = [False]

        def tick():
            if window._job or not window.review:
                return
            if phase[0] == 0:
                item = next(
                    window.files.topLevelItem(i)
                    for i, change in enumerate(window.patch.files)
                    if change.path.endswith("notes.py")
                )
                window.files.setCurrentItem(item)
                phase[0] = 1
                return
            if window.diff.rendered.left:
                # sample-only presentation path; no real user repository is involved
                window.repos.setItemText(
                    window.repos.currentIndex(),
                    "C:\\Projects\\notes-cli   ·   main   ·   ready",
                )
                window.ack.setChecked(True)
                output.parent.mkdir(parents=True, exist_ok=True)
                captured[0] = window.grab().save(str(output))
                timer.stop()
                window.close()

        timer = QTimer(window)
        timer.timeout.connect(tick)
        timer.start(100)
        QTimer.singleShot(15000, app.quit)
        app.exec()
        if not captured[0]:
            print("Screenshot capture did not complete.", file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
