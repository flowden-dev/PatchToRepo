# Development and packaging

Use Python 3.12 x64 and Git. Python 3.11–3.13 are covered by the CI configuration.
Runtime dependencies are Qt for Python Essentials 6.8.3 and Pygments 2.21.0.
Dependencies are pinned in `pyproject.toml`; no web service is used at runtime.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux:   source .venv/bin/activate
python -m pip install -e '.[dev,packaging]'
python -m patchtorepo
```

The normal no-argument launch opens the UI; it does not install a menu or modify
any repository. Use an isolated settings directory for development:

```powershell
$env:PATCHTOREPO_DATA = "$env:TEMP\patch-to-repo-development"
python -m patchtorepo "C:\Downloads\example.patch"
```

`--smoke-test` creates a disposable repository, loads a sample patch, renders a
real code comparison and exits. It bypasses normal preferences, legacy import,
Explorer integration and the single-instance server.

## Checks

```sh
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m build
python -m patchtorepo --smoke-test
```

Set `QT_QPA_PLATFORM=offscreen` on a headless host. Tests use actual Git processes
and isolated temporary repositories. Windows boundary tests create unique test
registry paths and temporary Start menu shortcut locations, never production
keys or shortcuts. The single-instance process test is skipped only when a
host's sandbox forbids Unix-domain sockets.

`python scripts/demo.py` renders `docs/screenshot.png` from synthetic disposable
files. It never opens the user's repository. It is a screenshot of the actual Qt
application; the displayed repository path is a demonstration label.

## Build a desktop application

On Windows, **Build-Windows.cmd** creates an isolated build environment and runs
the packaging script. Alternatively:

```sh
python -m pip install '.[packaging]'
python scripts/build.py
```

PyInstaller creates `dist/PatchToRepo/`, smoke-tests the executable, and produces
a ZIP plus SHA-256 file. Build on the target OS; this is not a cross-compiler.
Keep the EXE and `_internal` directory together. The Windows bundle retains
replaceable Qt libraries; it does not use a one-file/self-extracting distribution.
Git remains an external dependency.

Build artifacts include the project license, third-party notices, GNU license
texts and discovered dependency license files. Before distributing a binary,
complete the Qt/PySide corresponding-source and licensing steps documented in
[third-party notices](../THIRD_PARTY_NOTICES.md).

CI uses read-only repository permissions and immutable action commit pins. It
runs the test matrix first, then uploads a Windows build artifact. Publishing a
release is a separate maintainer action. No tokens, repository URLs or accounts
are required for the application itself.

## Manual Windows acceptance

Before announcing a Windows release, check on Windows 10 x64:

1. Install with a normal user account; launch from Explorer and the Start menu
2. Open `.patch`, `.diff` and a Git-format `.mpatch` in paths with spaces/non-ASCII text
3. Import AutoIt history and use both a unique match and multiple matching clones
4. Review text, binary, add/delete/rename changes; test 100%, 150% and 200% DPI
5. Apply to a disposable repository and verify unchanged index/history
6. Modify a reviewed file externally, then confirm Apply refuses the stale review
7. Open another patch while busy; confirm it is queued without replacing the active one
8. Reinstall from a different folder; move the downloaded source and verify the menu still works
9. Remove integration; check default associations, unrelated shortcuts and repositories remain intact
10. Build and smoke-test the EXE; open it interactively and inspect syntax highlighting

Linux engine/UI checks do not prove Explorer, PowerShell shortcut creation,
Windows file locking, Windows filesystem semantics or DPI behavior.

### Scrolling and rapid application acceptance

On Windows, compare long lines and scroll each horizontal scrollbar while the
window stays focused: both text panes must move immediately. Repeat vertically
and with unequal line lengths. At 100%, 125% and 150% scaling, confirm that the
footer remains readable and review confirmation is next to Apply.

Toggle Close after apply, restart and confirm it is remembered. A verified
application closes when enabled; a failed check/apply or unverified result must
remain visible. If another patch was queued, the window stays open.

### Change overview acceptance

Compare a long file with changes near the beginning, middle and end. Both scrollbars
must show red/green locations even when those changes are outside the visible
text. Click each marker from either pane; verify both panes jump, retain their
horizontal positions and still repaint when scrolled. Drag the thumb by its
clear left edge; grabbing it must not jump first. Click a marker that overlaps
the thumb, then drag the blank track. Use the mouse wheel over both the code and
scrollbar, and test Up/Down/Home/End with the scrollbar focused. Check the toolbar's
change position and −/+ badges for a −7/+80 replacement, insertion, deletion and
binary file. Compare short lines on one side with long lines on the other and
verify matching viewport heights and vertical positions at the end of the file.
Switch files and resize the window to confirm markers never remain stale.
