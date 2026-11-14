"""Build with isolated dependencies so the user's Python stays unchanged."""

import os
import subprocess
import sys
import venv
from pathlib import Path

if not (3, 11) <= sys.version_info[:2] < (3, 14):
    raise SystemExit("Use Python 3.11–3.13. Python 3.12 x64 is recommended.")

root = Path(__file__).resolve().parents[1]
folder = root / ".venv-build"
venv.EnvBuilder(with_pip=True).create(folder)
python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
subprocess.run([str(python), "-m", "pip", "install", str(root) + "[packaging]"], check=True)
subprocess.run([str(python), str(root / "scripts/build.py")], check=True)
