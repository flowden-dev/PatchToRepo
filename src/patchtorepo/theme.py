from pathlib import Path

STYLE = """
QWidget { background: #111722; color: #dbe3f1; }
QMainWindow, QDialog { background: #111722; }
QMenuBar { background: #111722; color: #a1adc2; padding: 3px 8px; }
QMenuBar::item:selected, QMenu::item:selected { background: #343255; }
QMenu { background: #1b2331; border: 1px solid #39445a; padding: 5px; }
QMenu::item { padding: 7px 30px 7px 15px; }
QLabel#brand { font-size: 19pt; font-weight: 600; color: #f2f5fc; }
QLabel#subtle { color: #8d9bb2; }
QLabel#section { color: #b2bfd3; font-weight: 600; }
QLabel#fileTitle { font-weight: 600; font-size: 11pt; padding: 8px 4px; }
QLabel#paneTitle { background: #1a2231; color: #93a3bd; font-size: 8pt; font-weight: 600; padding: 9px 6px; }
QWidget#paneHeader { background: #1a2231; }
QLabel#removedCount { background: #3b242e; color: #ff9aaa; border: 1px solid #653a48; border-radius: 4px; padding: 3px 7px; font-weight: 600; }
QLabel#addedCount { background: #18382f; color: #80e3b8; border: 1px solid #2c5a49; border-radius: 4px; padding: 3px 7px; font-weight: 600; }
QLabel#diffNote { background: #1a2231; color: #91a0b7; font-size: 8pt; padding: 8px; }
QPushButton, QToolButton { background: #222d3e; border: 1px solid #344157; border-radius: 6px; padding: 6px 11px; min-height: 18px; }
QPushButton:hover, QToolButton:hover { background: #303e54; border-color: #5b6b86; }
QPushButton:pressed { background: #38465e; }
QPushButton:disabled, QToolButton:disabled { color: #56637a; background: #1a2230; border-color: #293346; }
QPushButton#primary { background: #8873ed; color: #fff; border-color: #9985f5; font-weight: 600; padding: 7px 22px; }
QPushButton#primary:hover { background: #9b88f8; }
QPushButton#primary:disabled { color: #716c92; background: #302b49; border-color: #3c3558; }
QPushButton#quiet { background: transparent; border-color: #2e3a4d; }
QLineEdit, QComboBox, QSpinBox { background: #192231; color: #dde6f5; border: 1px solid #35415a; border-radius: 5px; padding: 7px; selection-background-color: #544c83; }
QLineEdit:focus, QComboBox:focus { border-color: #9683ec; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #1e293a; selection-background-color: #3a355e; }
QTreeWidget { background: #151d2b; border: 1px solid #2a3548; border-radius: 5px; outline: none; selection-background-color: #353152; }
QTreeWidget::item { padding: 9px 5px; border-bottom: 1px solid #1f2939; }
QTreeWidget::item:selected { background: #363152; color: #f1edff; }
QTreeWidget::item:hover { background: #252c40; }
QHeaderView::section { background: #1c2637; color: #8798b3; border: 0; padding: 7px; font-size: 8pt; }
QPlainTextEdit { background: #161e2b; color: #dbe4f3; border: 1px solid #2b374a; selection-background-color: #4b5273; }
QTabWidget::pane { border: 1px solid #2b374a; background: #161e2b; }
QTabBar::tab { background: transparent; color: #8c9db7; padding: 10px 17px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #d4caff; border-bottom-color: #aa93ff; }
QTabBar::tab:hover { color: #e4dfff; }
QSplitter::handle { background: #111722; width: 5px; height: 5px; }
QScrollBar:vertical { background: #151c28; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #3b475d; min-height: 30px; border-radius: 5px; }
QScrollBar:horizontal { background: #151c28; height: 14px; margin: 0; }
QScrollBar::handle:horizontal { background: #3b475d; min-width: 40px; border-radius: 5px; }
QScrollBar::handle:hover { background: #596984; }
QScrollBar::handle:pressed { background: #8873ed; }
QScrollBar#changeOverview:vertical { width: 22px; background: #111925; }
QScrollBar#changeOverview::handle:vertical { background: #263346; border: 1px solid #5b6b84; border-radius: 2px; min-height: 30px; }
QScrollBar#changeOverview::handle:vertical:hover { background: #35465f; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #596480; border-radius: 4px; background: #1b2537; }
QCheckBox::indicator:checked { background: #8d78ec; border-color: #b6a7ff; }
QCheckBox:disabled { color: #66748d; }
QProgressBar { background: #1c2739; border: 0; height: 3px; }
QProgressBar::chunk { background: #a48af5; }
QToolTip { background: #28344a; color: #eef2f9; border: 1px solid #50617e; padding: 5px; }
"""

_RESOURCES = Path(__file__).resolve().parent / "resources"
STYLE += f'''
QCheckBox::indicator:checked {{ image: url("{(_RESOURCES / "check.svg").as_posix()}"); }}
QComboBox::down-arrow {{ image: url("{(_RESOURCES / "chevron.svg").as_posix()}"); width: 12px; height: 12px; }}
'''
