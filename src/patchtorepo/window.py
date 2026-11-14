from __future__ import annotations

import logging
import os
import traceback
from collections import deque
from pathlib import Path

from PySide6.QtCore import QByteArray, QSignalBlocker, Qt, QThread, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .diff import display_text, render
from .engine import Applied, ApplyError, Engine, Review
from .git import Git
from .integration import install_menu, uninstall_menu
from .overview import ChangeCountDelegate, counts_html
from .patch import Patch
from .storage import Store
from .widgets import DiffView


class Job(QThread):
    def __init__(self, work, parent):
        super().__init__(parent)
        self.work = work
        self.value = None
        self.error = None
        self.trace = ""

    def run(self):
        try:
            self.value = self.work()
        except Exception as exc:
            self.error = exc
            self.trace = traceback.format_exc()


class PatchHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        color = (
            "#71d1a4"
            if text.startswith("+")
            else "#ef92a2"
            if text.startswith("-")
            else "#b7a1ff"
            if text.startswith(("@@", "diff --git"))
            else "#91a6c6"
            if text.startswith(("index ", "new file", "rename "))
            else None
        )
        if color:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.setFormat(0, len(text.encode("utf-16-le")) // 2, fmt)


class MainWindow(QMainWindow):
    def __init__(self, store: Store, initial: str | None = None):
        super().__init__()
        self.store = store
        self.engine: Engine | None = None
        self.patch: Patch | None = None
        self.review: Review | None = None
        self._job: Job | None = None
        self._queue: deque[str] = deque()
        self._seen: set[int] = set()
        self._render_cache = {}
        self._draft_dirty = False
        self._draft_editable = False
        self._source_loading = False
        self._source_editing = False
        self._applied = False
        self._closing = False
        self._last_backup: Path | None = None
        self.setWindowTitle(f"Patch to Repo {__version__}")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "resources/app.ico")))
        self.resize(1420, 900)
        self.setMinimumSize(960, 620)
        self.setAcceptDrops(True)
        self._build()
        for editor in (self.diff.left, self.diff.right):
            editor.set_code_font(self.store.get("font_size", 11))
        geometry = self.store.get("geometry")
        if isinstance(geometry, str):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        self._refresh_repos()
        QTimer.singleShot(0, lambda: self._initialize(initial))

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 10, 20, 14)
        layout.setSpacing(12)
        top = QHBoxLayout()
        brand = QLabel("Patch to Repo")
        brand.setObjectName("brand")
        top.addWidget(brand)
        top.addStretch()
        self.open_button = self._button("Open patch…", self.open_dialog)
        self.next_patch = self._button("Open next", self._open_next)
        self.next_patch.hide()
        self.settings_button = self._button("Settings", self.settings)
        top.addWidget(self.next_patch)
        top.addWidget(self.open_button)
        top.addWidget(self.settings_button)
        layout.addLayout(top)
        patch_row = QHBoxLayout()
        self.patch_label = QLabel("Drop a patch here, or open one from Explorer.")
        self.patch_label.setObjectName("subtle")
        self.patch_label.setTextFormat(Qt.TextFormat.PlainText)
        self.patch_label.setWordWrap(True)
        patch_row.addWidget(self.patch_label, 1)
        self.summary = QLabel("")
        self.summary.setObjectName("section")
        patch_row.addWidget(self.summary)
        layout.addLayout(patch_row)
        repo_row = QHBoxLayout()
        repo_row.addWidget(QLabel("Repository"))
        self.repos = QComboBox()
        self.repos.setMinimumContentsLength(20)
        self.repos.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.repos.setPlaceholderText("Select or add a repository")
        self.repos.setAccessibleName("Repository")
        self.repos.currentIndexChanged.connect(self._repo_changed)
        repo_row.addWidget(self.repos, 1)
        self.add_button = self._button("Add…", self.add_repo)
        self.detect_button = self._button("Find match", self.detect)
        self.check_button = self._button("Check again", self.check)
        repo_row.addWidget(self.add_button)
        repo_row.addWidget(self.detect_button)
        repo_row.addWidget(self.check_button)
        layout.addLayout(repo_row)
        self.status_label = QLabel("Starting…")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setContentsMargins(12, 9, 12, 9)
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        self.file_count = QLabel("Changes")
        self.file_count.setObjectName("section")
        side.addWidget(self.file_count)
        self.file_filter = QLineEdit()
        self.file_filter.setPlaceholderText("Filter files…")
        self.file_filter.setClearButtonEnabled(True)
        self.file_filter.textChanged.connect(self._filter_files)
        side.addWidget(self.file_filter)
        self.files = QTreeWidget()
        self.files.setColumnCount(2)
        self.files.setHeaderLabels(["File", "Changes"])
        self.files.setItemDelegateForColumn(1, ChangeCountDelegate(self.files))
        self.files.setRootIsDecorated(False)
        self.files.setAlternatingRowColors(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files.currentItemChanged.connect(self._file_changed)
        side.addWidget(self.files, 1)
        self.viewed = QLabel("No patch loaded")
        self.viewed.setObjectName("subtle")
        side.addWidget(self.viewed)
        self.splitter.addWidget(sidebar)
        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(8, 0, 0, 0)
        content.setSpacing(5)
        self.file_title = QLabel("Changes will appear here")
        self.file_title.setObjectName("fileTitle")
        self.file_title.setTextFormat(Qt.TextFormat.PlainText)
        self.file_title.setWordWrap(True)
        content.addWidget(self.file_title)
        self.tabs = QTabWidget()
        compare = QWidget()
        comparison = QVBoxLayout(compare)
        comparison.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 7, 8, 7)
        self.prev_change = self._button("↑", lambda: self.diff.navigate(-1))
        self.next_change = self._button("↓", lambda: self.diff.navigate(1))
        for button, text in (
            (self.prev_change, "Previous change · Shift+F8"),
            (self.next_change, "Next change · F8"),
        ):
            button.setToolTip(text)
            button.setAccessibleName(text)
        toolbar.addWidget(self.prev_change)
        toolbar.addWidget(self.next_change)
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Find in code  ·  Enter")
        self.find_text.setMaximumWidth(230)
        self.find_text.returnPressed.connect(self._find)
        toolbar.addWidget(self.find_text)
        toolbar.addStretch()
        self.encoding = QComboBox()
        self.encoding.addItems(["Auto", "utf-8", "cp1252", "cp949", "latin-1", "utf-16"])
        self.encoding.setToolTip("Display encoding only. Patch and file bytes are preserved.")
        self.encoding.currentTextChanged.connect(self._encoding_changed)
        toolbar.addWidget(self.encoding)
        comparison.addLayout(toolbar)
        self.diff = DiffView()
        self.diff.layout().removeWidget(self.diff.summary)
        toolbar.insertWidget(2, self.diff.summary)
        comparison.addWidget(self.diff, 1)
        self.tabs.addTab(compare, "Compare")
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(8, 8, 8, 8)
        source_toolbar = QHBoxLayout()
        self.edit_button = self._button("Edit draft", self._edit_draft)
        self.use_draft = self._button("Check edited draft", self._use_draft)
        self.discard_draft = self._button("Discard edits", self._discard_draft)
        self.save_copy = self._button("Save copy…", self._save_copy)
        for button in (self.edit_button, self.use_draft, self.discard_draft, self.save_copy):
            source_toolbar.addWidget(button)
        source_toolbar.addStretch()
        source_layout.addLayout(source_toolbar)
        self.source_note = QLabel(
            "Original file is preserved. Draft changes require a new check and review."
        )
        self.source_note.setObjectName("subtle")
        self.source_note.setWordWrap(True)
        source_layout.addWidget(self.source_note)
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.source.setFont(QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 10))
        self.source_highlighter = PatchHighlighter(self.source.document())
        self.source.textChanged.connect(self._source_changed)
        source_layout.addWidget(self.source, 1)
        self.tabs.addTab(source_page, "Patch source")
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setFont(QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 10))
        self.tabs.addTab(self.diagnostics, "Diagnostics")
        content.addWidget(self.tabs, 1)
        self.splitter.addWidget(main)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([310, 1070])
        layout.addWidget(self.splitter, 1)
        bottom = QHBoxLayout()
        self.ack = QCheckBox("I have reviewed the changes")
        self.ack.stateChanged.connect(self._controls)
        bottom.addStretch()
        self.backup_button = self._button("Recovery copies", self._open_backups)
        bottom.addWidget(self.backup_button)
        self.folder_button = self._button("Open repository", self._open_repo)
        bottom.addWidget(self.folder_button)
        options = QVBoxLayout()
        options.setSpacing(5)
        options.addWidget(self.ack)
        self.close_after_apply = QCheckBox("Close after apply")
        self.close_after_apply.setChecked(self.store.get("close_after_apply", False) is True)
        self.close_after_apply.setToolTip(
            "Remember this choice. Close after verified success; stay open on failure or when patches are queued."
        )
        self.close_after_apply.toggled.connect(self._set_close_after_apply)
        options.addWidget(self.close_after_apply)
        bottom.addSpacing(12)
        bottom.addLayout(options)
        self.apply_button = self._button("Apply patch", self.apply)
        self.apply_button.setObjectName("primary")
        self.apply_button.setToolTip("Apply to working files · Ctrl+Enter")
        bottom.addWidget(self.apply_button)
        layout.addLayout(bottom)
        QWidget.setTabOrder(self.folder_button, self.close_after_apply)
        QWidget.setTabOrder(self.close_after_apply, self.ack)
        QWidget.setTabOrder(self.ack, self.apply_button)
        file_menu = self.menuBar().addMenu("File")
        self._action(file_menu, "Open patch…", "Ctrl+O", self.open_dialog)
        self._action(file_menu, "Save patch copy…", "Ctrl+Shift+S", self._save_copy)
        self._action(file_menu, "Settings…", "Ctrl+,", self.settings)
        self._action(file_menu, "Exit", "Alt+F4", self.close)
        review_menu = self.menuBar().addMenu("Review")
        self._action(review_menu, "Check again", "F5", self.check)
        self._action(review_menu, "Next change", "F8", lambda: self.diff.navigate(1))
        self._action(review_menu, "Previous change", "Shift+F8", lambda: self.diff.navigate(-1))
        self._action(review_menu, "Find in code", "Ctrl+F", self.find_text.setFocus)
        self._action(review_menu, "Apply reviewed patch", "Ctrl+Return", self.apply)
        help_menu = self.menuBar().addMenu("Help")
        self._action(help_menu, "Quick guide", "F1", self.help)
        self._controls()

    @staticmethod
    def _button(text, slot):
        button = QPushButton(text)
        button.clicked.connect(slot)
        return button

    def _action(self, menu, label, shortcut, slot):
        action = QAction(label, self)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)

    def _status(self, text, tone="info"):
        palettes = {
            "info": ("#1d293e", "#b5c8eb"),
            "ok": ("#17382f", "#88dfb6"),
            "warn": ("#3c3020", "#f0c681"),
            "error": ("#3b2431", "#f4a2b2"),
        }
        bg, fg = palettes[tone]
        self.status_label.setStyleSheet(f"background:{bg};color:{fg};border-radius:6px;")
        self.status_label.setText(text)

    def _controls(self, *_):
        busy = self._job is not None
        self.close_after_apply.setEnabled(not busy)
        has_patch = self.patch is not None
        for button in (self.prev_change, self.next_change):
            button.setEnabled(not busy and bool(self.diff.rendered.changes))
        ready = bool(
            self.review
            and self._review_target_matches()
            and not self._draft_dirty
            and not self._applied
        )
        for control in (
            self.open_button,
            self.settings_button,
            self.add_button,
            self.repos,
            self.file_filter,
            self.files,
            self.encoding,
            self.next_patch,
        ):
            control.setEnabled(not busy)
        self.detect_button.setEnabled(
            not busy and has_patch and self.engine is not None and not self._draft_dirty
        )
        self.check_button.setEnabled(
            not busy
            and has_patch
            and self.engine is not None
            and self.repos.currentIndex() >= 0
            and not self._draft_dirty
        )
        self.ack.setEnabled(not busy and ready)
        self.apply_button.setEnabled(not busy and ready and self.ack.isChecked())
        self.edit_button.setEnabled(not busy and self._draft_editable and self.source.isReadOnly())
        self.use_draft.setEnabled(not busy and self._draft_dirty)
        self.discard_draft.setEnabled(not busy and self._draft_dirty)
        self.save_copy.setEnabled(not busy and has_patch)
        self.folder_button.setEnabled(self.repos.currentIndex() >= 0)
        self.source.setReadOnly(busy or not self._draft_editable or not self._source_editing)
        self.progress.setVisible(busy)
        self.next_patch.setVisible(bool(self._queue))
        self.next_patch.setText(f"Open next ({len(self._queue)})")
        self.viewed.setText(
            f"{len(self._seen)} of {len(self.patch.files)} files opened"
            if has_patch
            else "No patch loaded"
        )

    def _run(self, message, work, success, failure=None):
        if self._job:
            return
        self._status(message)
        job = Job(work, self)
        self._job = job

        def finished():
            self._job = None
            self._controls()
            if job.error is not None:
                self.diagnostics.appendPlainText(str(job.error))
                logging.getLogger(__name__).error(
                    "Background operation: %s\n%s", job.error, job.trace
                )
                if isinstance(job.error, ApplyError) and job.error.backup:
                    self._last_backup = job.error.backup
                    self.diagnostics.appendPlainText(f"Recovery bundle: {job.error.backup}")
                if failure:
                    failure(job.error)
                else:
                    self._status(str(job.error).splitlines()[0], "error")
            else:
                success(job.value)
            job.deleteLater()
            self._controls()

        job.finished.connect(finished)
        self._controls()
        job.start()

    def _initialize(self, initial=None):
        def success(engine):
            self.engine = engine
            self._status("Open a patch to detect its repository and review the changes.")
            if initial:
                self.open_path(initial)

        def failed(error):
            self._status(str(error).splitlines()[0], "error")
            if initial:
                self.open_path(initial)

        self._run(
            "Locating Git…",
            lambda: Engine(Git(self.store.get("git", "")), self.store.folder),
            success,
            failed,
        )

    def _save(self, action):
        try:
            action()
            return True
        except Exception as exc:
            self.diagnostics.appendPlainText(f"Preferences could not be saved: {exc}")
            self._status(f"Preferences could not be saved: {exc}", "error")
            QMessageBox.warning(self, "Preferences could not be saved", str(exc))
            return False

    def _review_target_matches(self):
        selected = self.repos.currentData()
        return bool(
            self.review
            and selected
            and os.path.normcase(os.path.normpath(selected))
            == os.path.normcase(os.path.normpath(str(self.review.repo.root)))
        )

    def _invalidate_review(self, message):
        self.review = None
        self._render_cache.clear()
        self._seen.clear()
        self.ack.setChecked(False)
        self.diff.clear(message)
        self.file_title.setText("Repository check required")
        self._controls()

    def _refresh_repos(self, selected=None, candidates=()):
        self.repos.blockSignals(True)
        self.repos.clear()
        known = {str(c.root): c for c in candidates}
        paths = list(dict.fromkeys([str(c.root) for c in candidates] + self.store.repos()))
        for path in paths:
            c = known.get(path)
            state = f"  ·  {c.branch}  ·  {c.status}" if c else ""
            self.repos.addItem(path + state, path)
            if c:
                self.repos.setItemData(
                    self.repos.count() - 1, c.reason or "Check passed", Qt.ItemDataRole.ToolTipRole
                )
        index = self.repos.findData(str(selected)) if selected else -1
        self.repos.setCurrentIndex(index)
        self.repos.blockSignals(False)
        if self.review and not self._review_target_matches():
            self._invalidate_review("Repository changed. Run Check again before applying.")

    def _can_replace(self):
        if self._job:
            return False
        if self._draft_dirty:
            return (
                QMessageBox.question(
                    self,
                    "Discard patch edits?",
                    "The patch draft has unchecked edits. Discard them?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                == QMessageBox.StandardButton.Discard
            )
        return True

    def open_dialog(self):
        if self._job:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open patch", "", "Patches (*.patch *.diff *.mpatch);;All files (*)"
        )
        if path:
            self.open_path(path)

    def open_path(self, path):
        if self._job:
            self.enqueue(path)
            return
        if not self._can_replace():
            return
        self._run("Reading patch…", lambda: Patch.read(Path(path)), self._loaded)

    def enqueue(self, path):
        if not self.patch and not self._job and QApplication.activeModalWidget() is None:
            self.open_path(path)
        elif len(self._queue) < 20:
            self._queue.append(path)
            self._controls()
        else:
            self._status(
                "Incoming patch queue is full. Open the additional patch manually.", "warn"
            )

    def _open_next(self):
        if self._queue and self._can_replace():
            path = self._queue.popleft()
            # retain the active draft until the replacement has actually loaded
            self._run("Reading patch…", lambda: Patch.read(Path(path)), self._loaded)
            self._controls()

    def _loaded(self, patch):
        self.patch = patch
        self.review = None
        self._applied = False
        self._draft_dirty = False
        self._seen.clear()
        self._render_cache.clear()
        self.ack.setChecked(False)
        self.patch_label.setText(patch.name)
        self.patch_label.setToolTip(f"SHA-256 {patch.digest}")
        binary_count = sum(f.binary for f in patch.files)
        summary = f"{len(patch.files)} files"
        if binary_count < len(patch.files):
            summary += " &nbsp;&nbsp; " + counts_html(
                sum(f.removed for f in patch.files), sum(f.added for f in patch.files)
            )
        if binary_count:
            summary += f" &nbsp; · &nbsp; {binary_count} binary"
        self.summary.setText(summary)
        self.file_count.setText(f"Changes  ·  {len(patch.files)}")
        with QSignalBlocker(self.file_filter):
            self.file_filter.clear()
        self.files.blockSignals(True)
        self.files.clear()
        for i, change in enumerate(patch.files):
            info = "binary" if change.binary else f"−{change.removed:,}  +{change.added:,}"
            parent = str(Path(change.path).parent)
            name = Path(change.path).name + (f"\n{parent}" if parent != "." else "")
            item = QTreeWidgetItem([name, info])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            item.setToolTip(0, f"{change.kind}: {change.old or '∅'} → {change.new or '∅'}")
            if not change.binary:
                item.setData(1, Qt.ItemDataRole.UserRole, (change.removed, change.added))
                item.setToolTip(
                    1, f"Patch: {change.removed:,} lines removed, {change.added:,} lines added"
                )
            self.files.addTopLevelItem(item)
        self.files.blockSignals(False)
        self._load_source()
        self.diagnostics.setPlainText(f"Patch: {patch.name}\nSHA-256: {patch.digest}\n")
        self.diff.clear("Repository check is required for an actual before/after preview.")
        self.file_title.setText("Select a repository to build the preview")
        if self.engine:
            self.detect()
        else:
            self._status("Patch loaded. Locate Git in Settings to check a repository.", "warn")
            self.tabs.setCurrentIndex(1)

    def _load_source(self):
        self._source_loading = True
        self._source_editing = False
        try:
            raw = self.patch.data
            self._draft_editable = len(raw) <= 512 * 1024 and b"\r" not in raw
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", "replace")
                self._draft_editable = False
            preview = text[: 2 * 1024 * 1024].replace("\r\n", "\n")
            visible = display_text(preview)
            escaped = visible != preview
            limited = len(raw) > 2 * 1024 * 1024 or len(visible) > 2 * 1024 * 1024
            self.source.setPlainText(visible[: 2 * 1024 * 1024])
            self._draft_editable = (
                self._draft_editable
                and not escaped
                and self.source.toPlainText().encode("utf-8") == raw
            )
            self.source.setReadOnly(True)
            self.source_note.setText(
                "Source preview truncated at 2 MiB. Save a copy to inspect all patch bytes."
                if limited
                else "Control characters are shown as ⟦U+…⟧ labels. Read-only source; Save copy preserves every byte."
                if escaped
                else "Draft edits use UTF-8/LF. Hunk counts must stay valid. Original file is preserved."
                if self._draft_editable
                else "Read-only source: editing requires a UTF-8/LF patch of at most 512 KiB. Application preserves the original bytes."
            )
        finally:
            self._source_loading = False

    def detect(self):
        if self._job or not self.patch or not self.engine or self._draft_dirty:
            return
        self.review = None
        self.ack.setChecked(False)
        patch, engine, repos = self.patch, self.engine, self.store.repos()
        if not repos:
            self._status(
                "Add your repository once. Future patches will be checked against your saved repositories."
            )
            self.tabs.setCurrentIndex(1)
            self._controls()
            return

        def done(candidates):
            matches = [c for c in candidates if c.status == "ready"]
            self.diagnostics.appendPlainText(
                "Repository matching (other repositories are expected not to match):\n"
                + "\n".join(f"{c.root}: {c.status}" for c in candidates)
                + "\nSelect a repository and run Check for its detailed result."
            )
            selected = matches[0].root if len(matches) == 1 else None
            # an unsuccessful path match is a hint, never a ready selection
            if not matches and candidates and candidates[0].score > 0:
                selected = candidates[0].root
            self._refresh_repos(selected, candidates)
            if len(matches) == 1:
                self.check()
            elif len(matches) > 1:
                self._status(
                    f"{len(matches)} repositories match. Choose the intended repository to continue.",
                    "warn",
                )
                self.diff.clear("Multiple compatible repositories. Select one above.")
            else:
                self._status(
                    "No saved repository passes. Check the suggested path or add the correct repository. See Diagnostics.",
                    "warn",
                )
                self.tabs.setCurrentIndex(1)

        self._run(
            f"Checking {len(repos)} saved repositories…", lambda: engine.detect(repos, patch), done
        )

    def add_repo(self):
        if self._job:
            return
        folder = QFileDialog.getExistingDirectory(self, "Add repository")
        if not folder:
            return
        if not self.engine:
            self._status("Locate Git in Settings first.", "warn")
            return

        def done(repo):
            if not self._save(lambda: self.store.remember(repo.root)):
                return
            self._refresh_repos(repo.root)
            if self._draft_dirty:
                self._status(
                    "Repository selected. Check the edited draft, or discard edits and run Check again.",
                    "warn",
                )
            elif self.patch:
                self.check()
            else:
                self._status(f"Saved {repo.root}", "ok")

        self._run("Checking repository…", lambda: self.engine.repo_state(Path(folder)), done)

    def _repo_changed(self, *_):
        if self._job:
            return
        self._invalidate_review("Repository changed. A new check and review are required.")
        if self._draft_dirty:
            self._status(
                "Repository selected. Check the edited draft, or discard edits and run Check again.",
                "warn",
            )
        else:
            self.check()

    def check(self):
        if self._job or not self.engine or not self.patch or self._draft_dirty:
            return
        path = self.repos.currentData()
        if not path:
            self._status("Select the intended repository first.", "warn")
            return
        self.review = None
        self._seen.clear()
        self._render_cache.clear()
        self._applied = False
        self.ack.setChecked(False)
        patch, engine, root = self.patch, self.engine, Path(path)
        self.diff.clear("Building preview for the selected repository…")
        self.file_title.setText("Checking selected repository")
        self.diagnostics.setPlainText(f"Selected repository: {root}\nBuilding patch preview…")

        def done(review):
            self.review = review
            saved = self._save(lambda: self.store.remember(review.repo.root))
            # a legacy history entry may name a subfolder; bind the selector to Git's root
            with QSignalBlocker(self.repos):
                index = self.repos.currentIndex()
                self.repos.setItemData(index, str(review.repo.root))
                self.repos.setItemText(
                    index, f"{review.repo.root}  ·  {review.repo.branch_label}  ·  ready"
                )
                self.repos.setItemData(
                    index, review.diagnostics or "Check passed", Qt.ItemDataRole.ToolTipRole
                )
            self.diagnostics.appendPlainText(
                f"\nRepository: {review.repo.root}\nBranch: {review.repo.branch_label}\n{review.diagnostics or 'Forward check passed; reverse check did not apply.'}"
            )
            self._status(
                "Check passed. Review the changes, then apply when ready."
                + (" Git reported warnings; see Diagnostics." if review.diagnostics else ""),
                "warn" if review.diagnostics or not saved else "ok",
            )
            if not saved:
                self._status(
                    "Check passed, but repository history could not be saved. See Diagnostics.",
                    "warn",
                )
            self.tabs.setCurrentIndex(0)
            first = self.files.topLevelItem(0)
            if self.files.currentItem() == first:
                self._file_changed(first, None)
            else:
                self.files.setCurrentItem(first)

        def failed(error):
            self.file_title.setText("Preview could not be built")
            with QSignalBlocker(self.repos):
                index = self.repos.currentIndex()
                self.repos.setItemText(index, f"{root}  ·  check failed")
                self.repos.setItemData(index, str(error), Qt.ItemDataRole.ToolTipRole)
            self.diff.clear("Preview unavailable. See Patch source and Diagnostics.")
            self._status(str(error).splitlines()[0], "error")
            self.tabs.setCurrentIndex(2)

        self._run(
            "Checking and building the before/after preview…",
            lambda: engine.review(root, patch),
            done,
            failed,
        )

    def _file_changed(self, current, previous):
        if not current or self._job or not self.patch:
            return
        index = current.data(0, Qt.ItemDataRole.UserRole)
        change = self.patch.files[index]
        self.file_title.setText(f"{change.kind}  ·  {change.path}")
        if not self.review:
            self.diff.clear(
                "Check a repository to see the actual result. The full patch is available in Patch source."
            )
            return
        key = (index, self.encoding.currentText())
        line_counts = None if change.binary else (change.removed, change.added)
        if key in self._render_cache:
            self.diff.show_render(self._render_cache[key], line_counts)
            self._seen.add(index)
            self._controls()
            return
        before, after = self.review.pair(index)
        encoding = self.encoding.currentText()
        status = self.status_label.text()
        style = self.status_label.styleSheet()

        def done(rendered):
            # keep a small bounded cache rather than a second full patch in memory
            if len(self._render_cache) >= 8:
                self._render_cache.pop(next(iter(self._render_cache)))
            self._render_cache[key] = rendered
            self.diff.show_render(rendered, line_counts)
            self._seen.add(index)
            self.status_label.setStyleSheet(style)
            self.status_label.setText(status)

        def failed(error):
            self.review = None
            self.ack.setChecked(False)
            self.diff.clear("Comparison unavailable. See Diagnostics and run Check again.")
            self._status(str(error).splitlines()[0], "error")

        self.diff.clear("Preparing comparison…")
        self._run(
            "Preparing code comparison…",
            lambda: render(before, after, change.path, encoding),
            done,
            failed,
        )

    def _encoding_changed(self, *_):
        self._file_changed(self.files.currentItem(), None)

    def _filter_files(self, text):
        if not self.patch:
            return
        for i, change in enumerate(self.patch.files):
            self.files.topLevelItem(i).setHidden(text.casefold() not in change.path.casefold())

    def _find(self):
        found = self.diff.find(self.find_text.text())
        self.find_text.setToolTip("" if found else "No match in either pane")
        self.find_text.setStyleSheet("" if found else "border-color: #ee7989;")

    def _edit_draft(self):
        if self._job or not self._draft_editable:
            return
        self._source_editing = True
        self.source.setReadOnly(False)
        self.source.setFocus()
        self._controls()

    def _source_changed(self):
        if self._source_loading or self.source.isReadOnly():
            return
        self._draft_dirty = True
        self.ack.setChecked(False)
        self._status("Patch draft changed. Check the edited draft before applying.", "warn")
        self._controls()

    def _use_draft(self):
        if self._job or not self._draft_dirty:
            return
        raw = self.source.toPlainText().encode("utf-8")
        name = self.patch.name
        self._run("Validating edited patch…", lambda: Patch.parse(raw, name), self._loaded)

    def _discard_draft(self):
        if self._job or not self.patch:
            return
        self._draft_dirty = False
        self._load_source()
        self._status("Draft edits discarded. The loaded patch snapshot is restored.")
        if self.review is None:
            self._status("Draft edits discarded. Run Check again for the selected repository.")
        self._controls()

    def _save_copy(self):
        if self._job or not self.patch:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save patch copy", self.patch.name, "Patch (*.patch)"
        )
        if path:
            data = (
                self.source.toPlainText().encode("utf-8") if self._draft_dirty else self.patch.data
            )
            try:
                # stage in the same folder so failed writes do not truncate an existing file
                from .util import atomic_write

                atomic_write(Path(path), data)
            except OSError as exc:
                QMessageBox.warning(self, "Copy could not be saved", str(exc))

    def _set_close_after_apply(self, checked):
        if not self._save(lambda: self.store.set("close_after_apply", checked)):
            with QSignalBlocker(self.close_after_apply):
                self.close_after_apply.setChecked(not checked)

    def _close_after_success(self):
        if not self._applied or not self.close_after_apply.isChecked():
            return
        if self._queue:
            self._status(
                "Patch applied and verified. Queued patches remain; window kept open.", "ok"
            )
        elif not self._job and not self._draft_dirty:
            self.close()

    def apply(self):
        if (
            self._job
            or not self.review
            or not self.ack.isChecked()
            or self._draft_dirty
            or self._applied
        ):
            return
        if not self._review_target_matches():
            self._invalidate_review("The selected repository differs from this review.")
            self._status("Repository changed. Run Check again before applying.", "warn")
            return
        review, engine = self.review, self.engine
        self.review = None
        self.ack.setChecked(False)

        def done(result: Applied):
            self.review = review
            self._last_backup = result.backup
            self._applied = True
            self.diagnostics.appendPlainText(
                f"\n{result.diagnostics}\nRecovery bundle: {result.backup}"
            )
            self._status(
                "Patch applied and verified. Changes are ready in your working files."
                if result.verified
                else "Git reported success, but verification differs. Inspect Diagnostics and the recovery bundle.",
                "ok" if result.verified else "warn",
            )
            if result.verified and self.close_after_apply.isChecked():
                QTimer.singleShot(0, self._close_after_success)

        self._run(
            "Rechecking, saving recovery copies and applying…", lambda: engine.apply(review), done
        )

    def _open_repo(self):
        path = self.repos.currentData()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_backups(self):
        folder = self.store.folder / "backups"
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QMessageBox.information(
                self,
                "Recovery copies",
                "A recovery ZIP is saved here before each application. No patch has been applied yet.",
            )

    def settings(self):
        if self._job:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(650)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        git_path = QLineEdit(
            self.store.get("git", self.engine.git.executable if self.engine else "")
        )
        git_row = QHBoxLayout()
        git_row.addWidget(git_path)
        browse = self._button("Browse…", lambda: self._choose_git(git_path, dialog))
        git_row.addWidget(browse)
        form.addRow("Git executable", git_row)
        font_size = QSpinBox()
        font_size.setRange(8, 22)
        font_size.setValue(self.store.get("font_size", 11))
        form.addRow("Code font size", font_size)
        layout.addLayout(form)
        note = QLabel(
            "Explorer integration is installed for your Windows account.\nThe existing default application for opening patches is preserved."
        )
        note.setObjectName("subtle")
        layout.addWidget(note)
        integration = QHBoxLayout()
        install = self._button("Install / repair menu", lambda: self._integration(True, dialog))
        remove = self._button("Remove menu", lambda: self._integration(False, dialog))
        for button in (install, remove):
            button.setEnabled(os.name == "nt")
            integration.addWidget(button)
        layout.addLayout(integration)
        forget = self._button("Forget selected repository", lambda: self._forget_repo(dialog))
        forget.setEnabled(self.repos.currentIndex() >= 0)
        layout.addWidget(forget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_git = git_path.text().strip()
            new_font = font_size.value()

            def save_settings():
                git = Git(new_git)
                self.store.set_many({"git": git.executable, "font_size": new_font})
                return git

            def done(git):
                self.engine = Engine(git, self.store.folder)
                for editor in (self.diff.left, self.diff.right):
                    editor.set_code_font(new_font)
                self._invalidate_review("Settings changed. Run Check again before applying.")
                self._status("Settings saved. Run Check again before applying.")

            self._run("Validating and saving settings…", save_settings, done)
        dialog.deleteLater()

    def _choose_git(self, field, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent, "Locate Git", "", "Git (git.exe);;All files (*)"
        )
        if path:
            field.setText(path)

    def _forget_repo(self, dialog):
        path = self.repos.currentData()
        if path and self._save(lambda: self.store.forget(path)):
            self.review = None
            self.ack.setChecked(False)
            self._refresh_repos()
            dialog.reject()
            self._status("Repository removed from the saved list.")
            self._controls()

    def _integration(self, install, dialog):
        dialog.reject()

        def done(value):
            self._status(
                "Explorer menu installed. Right-click a patch and choose Review and apply patch."
                if install
                else "Explorer menu removed. Saved repositories and recovery files are retained.",
                "ok",
            )

        self._run(
            "Updating Explorer integration…",
            lambda: install_menu(self.store.folder) if install else uninstall_menu(),
            done,
        )

    def help(self):
        QMessageBox.information(
            self,
            "Quick guide",
            "1. Open a .patch file or drop it into the window.\n"
            "2. Add your repository once. A unique compatible match is selected automatically.\n"
            "3. Select files on the left. Red is the current content; green is the result.\n"
            "4. Use F8 / Shift+F8 to move between changes, or Ctrl+F to find code.\n"
            "5. Confirm that you reviewed the changes, then click Apply patch (Ctrl+Enter).\n\n"
            "Check again: F5. Patch source contains the complete diff for ordinary-sized patches. "
            "Edit draft lets you adjust supported text patches, then check them again.\n\n"
            "Apply leaves changes unstaged and uncommitted. Check success establishes textual "
            "compatibility; build and test the changed project afterward. Recovery ZIPs contain "
            "the original affected files and a manifest.\n\n"
            "On Windows 11, the Explorer command may appear under Show more options.",
        )

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.open_path(urls[0].toLocalFile())
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self._job:
            self._status("Wait for the current operation to finish before closing.", "warn")
            event.ignore()
            return
        if not self._can_replace():
            event.ignore()
            return
        self._save(
            lambda: self.store.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        )
        event.accept()
