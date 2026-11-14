import os
import uuid

import pytest

from patchtorepo import integration

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows boundary")


def test_registry_install_remove_uses_isolated_owned_keys(tmp_path, monkeypatch):
    import winreg

    base = rf"Software\PatchToRepoTests\{uuid.uuid4().hex}"
    monkeypatch.setattr(integration, "VERB", base + r"\{extension}\shell\PatchToRepo")
    monkeypatch.setattr(integration, "EXTENSIONS", (".patch",))
    monkeypatch.setattr(integration, "shortcut_directory", lambda: tmp_path / "shortcuts")
    target = integration.install_menu(tmp_path)
    key_path = base + r"\.patch\shell\PatchToRepo"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path + r"\command",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            command, _ = winreg.QueryValueEx(key, "")
            assert command.endswith(' -- "%1"')
            assert str(target) in command
        integration.uninstall_menu()
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        assert target.is_dir()
    finally:
        for key in (
            key_path + r"\command",
            key_path,
            base + r"\.patch\shell",
            base + r"\.patch",
            base,
        ):
            try:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, key, winreg.KEY_WOW64_64KEY, 0)
            except FileNotFoundError:
                pass


def test_windows_quote_roundtrip():
    import ctypes
    from ctypes import wintypes

    argv = [r"C:\Program Files\Python\pythonw.exe", r"C:\Tools & patches\launch.pyw"]
    command = integration.launch_command(argv).replace('"%1"', '"F:\\My patches\\café.patch"')
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    size = ctypes.c_int()
    pointer = parse(command, ctypes.byref(size))
    try:
        assert [pointer[i] for i in range(size.value)] == argv + [
            "--",
            "F:\\My patches\\café.patch",
        ]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(pointer)
