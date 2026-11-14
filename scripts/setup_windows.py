"""One-time, per-user source installation. Run through Setup-Windows.cmd."""

import os
import struct
import subprocess
import sys
import venv
from pathlib import Path


def main():
    if (
        os.name != "nt"
        or not (3, 11) <= sys.version_info[:2] < (3, 14)
        or struct.calcsize("P") != 8
    ):
        raise SystemExit(
            "Windows and Python 3.11–3.13 x64 are required. Python 3.12 x64 is recommended."
        )
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.environ["LOCALAPPDATA"]) / "PatchToRepo/runtime"
    python = runtime / "Scripts/python.exe"
    if not python.is_file():
        print("Creating a private Python environment...")
        venv.EnvBuilder(with_pip=True).create(runtime)
    print("Installing Patch to Repo and its dependencies...")
    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", str(root)], check=True)
    subprocess.run([str(python), "-m", "patchtorepo", "--install-menu"], check=True)
    subprocess.Popen([str(runtime / "Scripts/pythonw.exe"), "-m", "patchtorepo"])
    print("Installed. Right-click a patch and choose Review and apply patch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
