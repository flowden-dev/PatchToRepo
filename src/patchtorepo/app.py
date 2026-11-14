from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .integration import install_menu, uninstall_menu
from .storage import Store
from .theme import STYLE
from .window import MainWindow


class Instance:
    def __init__(self, store: Store):
        token = hashlib.sha256(str(store.folder.resolve()).encode()).hexdigest()[:24]
        self.name = "patchtorepo-" + token
        self.lock = QLockFile(str(store.folder / "instance.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer()
        self.sockets = {}

    def acquire(self, path: str | None) -> bool:
        if not self.lock.tryLock(0):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if not socket.waitForConnected(2000):
                raise OSError(
                    "Patch to Repo is already running but is not responding. Wait for startup and try again."
                )
            payload = json.dumps({"path": path}, ensure_ascii=True).encode() + b"\n"
            socket.write(payload)
            socket.flush()
            response = bytearray()
            deadline = time.monotonic() + 2
            while b"\n" not in response and time.monotonic() < deadline:
                if not socket.bytesAvailable():
                    socket.waitForReadyRead(max(1, int((deadline - time.monotonic()) * 1000)))
                response.extend(bytes(socket.readAll()))
                if len(response) > 16:
                    break
            if response != b"OK\n":
                raise OSError("The open window did not accept the patch. Try again in that window.")
            socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise OSError(self.server.errorString())
        return True

    def attach(self, window: MainWindow):
        def connected():
            while self.server.hasPendingConnections():
                socket = self.server.nextPendingConnection()
                self.sockets[socket] = bytearray()

                def read(s=socket):
                    buffer = self.sockets.get(s)
                    if buffer is None:
                        return
                    buffer.extend(bytes(s.readAll()))
                    if len(buffer) > 65536:
                        s.abort()
                        return
                    if b"\n" not in buffer:
                        return
                    try:
                        payload = json.loads(bytes(buffer))
                        path = payload.get("path")
                        if path is not None and (
                            not isinstance(path, str) or not Path(path).is_absolute()
                        ):
                            raise ValueError("invalid path")
                        if path and len(window._queue) >= 20:
                            s.write(b"FULL\n")
                        else:
                            if path:
                                window.enqueue(path)
                            window.showNormal()
                            window.raise_()
                            window.activateWindow()
                            s.write(b"OK\n")
                        s.flush()
                    except (ValueError, TypeError, AttributeError):
                        s.abort()
                    finally:
                        self.sockets.pop(s, None)

                def disconnected(s=socket):
                    self.sockets.pop(s, None)
                    s.deleteLater()

                socket.readyRead.connect(read)
                socket.disconnected.connect(disconnected)
                QTimer.singleShot(5000, socket, socket.disconnectFromServer)
                if socket.bytesAvailable():
                    read()

        self.server.newConnection.connect(connected)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review and apply a Git patch")
    parser.add_argument(
        "patch", nargs="?", help="Patch to open for review (never applied automatically)"
    )
    parser.add_argument("--version", action="version", version=__version__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install-menu", action="store_true")
    mode.add_argument("--uninstall-menu", action="store_true")
    mode.add_argument(
        "--smoke-test", action="store_true", help="Open an isolated test window and exit"
    )
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Patch to Repo")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10))
    app.setStyleSheet(STYLE)
    test_dir = (
        tempfile.TemporaryDirectory(prefix="patch-to-repo-smoke-") if args.smoke_test else None
    )
    handler = None
    instance = None
    previous_hook = sys.excepthook
    try:
        store = Store(Path(test_dir.name) if test_dir else None)
        if args.install_menu:
            install_menu(store.folder)
            return 0
        if args.uninstall_menu:
            uninstall_menu()
            return 0
        if not test_dir:
            store.import_legacy()
        handler = RotatingFileHandler(
            store.folder / "application.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
        )
        logging.getLogger("patchtorepo").addHandler(handler)
        logging.getLogger("patchtorepo").setLevel(logging.WARNING)
        initial = str(Path(args.patch).resolve()) if args.patch else None
        if test_dir:
            from .smoke import fixture

            repo, patch = fixture(Path(test_dir.name))
            store.remember(repo)
            initial = str(patch)
        instance = None if test_dir else Instance(store)
        if instance and not instance.acquire(initial):
            return 0
        window = MainWindow(store, initial)
        if instance:
            instance.attach(window)

        def report_exception(kind, value, trace):
            logging.getLogger("patchtorepo").error("Unhandled error", exc_info=(kind, value, trace))
            QMessageBox.critical(
                window,
                "Unexpected error",
                f"{value}\n\nDetails were saved in application.log. If Apply was active, inspect working files and recovery copies before retrying.",
            )

        sys.excepthook = report_exception
        window.show()
        if test_dir:
            timer = QTimer(window)

            def finish_smoke():
                if window._job is None and window.review and window.diff.rendered.left:
                    window.close()

            QTimer.singleShot(15000, lambda: app.exit(1))

            timer.timeout.connect(finish_smoke)
            timer.start(100)
        return app.exec()
    except Exception as exc:
        if args.smoke_test:
            print(str(exc), file=sys.stderr)
        else:
            QMessageBox.critical(None, "Patch to Repo could not start", str(exc))
        return 1
    finally:
        sys.excepthook = previous_hook
        if instance:
            instance.server.close()
            if instance.lock.isLocked():
                instance.lock.unlock()
        if handler:
            logging.getLogger("patchtorepo").removeHandler(handler)
            handler.close()
        if test_dir:
            test_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
