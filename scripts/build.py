"""Build an onedir application and release ZIP on the current operating system."""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "PatchToRepo",
        "--paths",
        str(root / "src"),
        "--collect-all",
        "pygments",
        "--collect-data",
        "patchtorepo",
        "--add-data",
        f"{root / 'src/patchtorepo/resources'}{os.pathsep}patchtorepo/resources",
        "--icon",
        str(root / "src/patchtorepo/resources/app.ico"),
        str(root / "scripts/entrypoint.py"),
    ]
    subprocess.run(command, cwd=root, check=True)
    folder = root / "dist/PatchToRepo"
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / name, folder / name)
    shutil.copytree(root / "licenses", folder / "licenses", dirs_exist_ok=True)
    for package in ("pygments", "pyinstaller", "shiboken6", "PySide6-Essentials"):
        metadata = distribution(package)
        for file in metadata.files or []:
            if any(s in str(file).lower() for s in ("/licenses/", "/copying", "/license.")):
                source = Path(metadata.locate_file(file))
                if source.is_file():
                    destination = folder / "licenses" / package / file.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    executable = folder / ("PatchToRepo.exe" if os.name == "nt" else "PatchToRepo")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run([str(executable), "--smoke-test"], env=env, cwd=folder, check=True, timeout=30)
    name = f"PatchToRepo-{version}-{platform.system().lower()}-{platform.machine().lower()}"
    archive = Path(
        shutil.make_archive(str(root / "dist" / name), "zip", root / "dist", "PatchToRepo")
    )
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Built and smoke-tested {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
