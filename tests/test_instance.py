import os
import socket
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

from patchtorepo.app import Instance
from patchtorepo.storage import Store


def test_second_process_hands_patch_to_existing_window(qtbot, tmp_path):
    if sys.platform != "win32":
        probe_path = tmp_path / "socket-permission-probe"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.bind(str(probe_path))
        except PermissionError:
            pytest.skip("execution sandbox disallows Unix-domain sockets")
        probe_path.unlink()
    store = Store(tmp_path / "prefs")
    instance = Instance(store)
    assert instance.acquire(None)

    class Window:
        _queue = deque()

        def enqueue(self, path):
            self._queue.append(path)

        def showNormal(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    window = Window()
    instance.attach(window)
    incoming = str(tmp_path / "a patch with spaces.patch")
    script = """
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from patchtorepo.app import Instance
from patchtorepo.storage import Store
app = QApplication([])
instance = Instance(Store(Path(sys.argv[1])))
raise SystemExit(1 if instance.acquire(sys.argv[2]) else 0)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(store.folder), incoming],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        qtbot.waitUntil(lambda: process.poll() is not None, timeout=10000)
        out, err = process.communicate()
        assert process.returncode == 0, (out, err)
        assert list(window._queue) == [incoming]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        instance.server.close()
        instance.lock.unlock()
