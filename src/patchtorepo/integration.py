"""Owned per-user Explorer verbs; importing this module has no side effects."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

EXTENSIONS = (".patch", ".diff", ".mpatch")
VERB = r"Software\Classes\SystemFileAssociations\{extension}\shell\PatchToRepo"


def launch_command(arguments: list[str]) -> str:
    # the placeholder is always quoted; list2cmdline alone would leave it bare
    if any("\x00" in arg or '"' in arg for arg in arguments):
        raise ValueError("Invalid launch path.")
    return subprocess.list2cmdline(arguments) + ' -- "%1"'


def _notify_shell() -> None:
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def install_menu(data_dir: Path) -> Path:
    if os.name != "nt":
        raise OSError("Explorer integration is available on Windows only.")
    import winreg

    # a versioned installation never overwrites a running executable/package
    parent = data_dir / "applications"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / uuid.uuid4().hex
    if getattr(sys, "frozen", False):
        source = Path(sys.executable).parent
        target.mkdir()
        shutil.copy2(Path(sys.executable), target / Path(sys.executable).name)
        if (source / "_internal").is_dir():
            shutil.copytree(source / "_internal", target / "_internal")
        executable = target / Path(sys.executable).name
        for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
            if (source / name).is_file():
                shutil.copy2(source / name, target / name)
        if (source / "licenses").is_dir():
            shutil.copytree(source / "licenses", target / "licenses")
        arguments = [str(executable)]
        icon = executable
    else:
        package = Path(__file__).resolve().parent
        target.mkdir()
        shutil.copytree(
            package, target / "patchtorepo", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        launcher = target / "launch.pyw"
        launcher.write_text(
            "from patchtorepo.app import main\nraise SystemExit(main())\n", encoding="utf-8"
        )
        executable = Path(sys.executable).with_name("pythonw.exe")
        if not executable.is_file():
            raise OSError(
                "pythonw.exe is missing. Install the standard Windows Python distribution."
            )
        arguments = [str(executable), str(launcher)]
        icon = target / "patchtorepo/resources/app.ico"
    command = launch_command(arguments)
    flags = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
    for extension in EXTENSIONS:
        base = VERB.format(extension=extension)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base, 0, flags) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "Review and apply patch…")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{icon}",0')
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Single")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base + r"\command", 0, flags) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    _notify_shell()
    _install_shortcuts(arguments, icon, target)
    return target


def uninstall_menu() -> None:
    if os.name != "nt":
        raise OSError("Explorer integration is available on Windows only.")
    import winreg

    errors = []
    for extension in EXTENSIONS:
        base = VERB.format(extension=extension)
        for key in (base + r"\command", base):
            try:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, key, winreg.KEY_WOW64_64KEY, 0)
            except FileNotFoundError:
                pass
            except OSError as exc:
                errors.append(str(exc))
    _notify_shell()
    try:
        _remove_shortcuts()
    except OSError as exc:
        errors.append(str(exc))
    if errors:
        raise OSError("Some menu entries could not be removed: " + "; ".join(errors))


def shortcut_directory() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Patch to Repo"


def _install_shortcuts(arguments: list[str], icon: Path, working: Path) -> None:
    import json

    folder = shortcut_directory()
    folder.mkdir(parents=True, exist_ok=True)
    # only static script text enters PowerShell; paths arrive as JSON data on stdin
    script = r"""
$ErrorActionPreference = 'Stop'
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$ws = New-Object -ComObject WScript.Shell
foreach ($entry in $p.entries) {
    $link = $ws.CreateShortcut($entry.path)
    $link.TargetPath = $p.target
    $link.Arguments = $entry.arguments
    $link.WorkingDirectory = $p.working
    $link.IconLocation = $p.icon
    $link.Description = 'Review and apply Git patches'
    $link.Save()
}
"""
    payload = {
        "target": arguments[0],
        "working": str(working),
        "icon": f'"{icon}",0',
        "entries": [
            {
                "path": str(folder / "Patch to Repo.lnk"),
                "arguments": subprocess.list2cmdline(arguments[1:]),
            },
            {
                "path": str(folder / "Remove context menu.lnk"),
                "arguments": subprocess.list2cmdline([*arguments[1:], "--uninstall-menu"]),
            },
        ],
    }
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps(payload).encode("ascii"),
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode:
        raise OSError(
            "Explorer menu installed, but Start menu shortcuts could not be created. "
            + result.stderr.decode("utf-8", "replace")
        )


def _remove_shortcuts() -> None:
    folder = shortcut_directory()
    for name in ("Patch to Repo.lnk", "Remove context menu.lnk"):
        (folder / name).unlink(missing_ok=True)
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
