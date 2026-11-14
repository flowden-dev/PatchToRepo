from concurrent.futures import ThreadPoolExecutor

from patchtorepo.integration import launch_command
from patchtorepo.storage import Store
from patchtorepo.util import atomic_write


def test_saved_history_is_unique_and_forget_preserves_repository(tmp_path):
    store = Store(tmp_path / "prefs")
    repo = tmp_path / "repo"
    repo.mkdir()
    file = repo / "important.txt"
    file.write_text("keep")
    store.remember(repo)
    store.remember(repo / ".")
    assert store.repos() == [str(repo)]
    store.forget(repo)
    assert store.repos() == []
    assert file.read_text() == "keep"


def test_concurrent_settings_writes_do_not_lose_other_keys(tmp_path):
    store = Store(tmp_path / "prefs")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.set(f"key{i}", i), range(30)))
    assert all(store.get(f"key{i}") == i for i in range(30))


def test_atomic_save_replaces_complete_file(tmp_path):
    path = tmp_path / "patch.patch"
    path.write_bytes(b"old")
    atomic_write(path, b"new")
    assert path.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [path]


def test_explorer_command_quotes_placeholder_and_paths():
    result = launch_command(
        [r"C:\Program Files\Python\pythonw.exe", r"C:\Tools & Stuff\launch.pyw"]
    )
    assert (
        result == '"C:\\Program Files\\Python\\pythonw.exe" "C:\\Tools & Stuff\\launch.pyw" -- "%1"'
    )


def test_conflicting_setup_modes_are_rejected_before_any_actions(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    env["PATCHTOREPO_DATA"] = str(tmp_path / "never-created")
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "patchtorepo", "--smoke-test", "--install-menu"],
        env=env,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert not (tmp_path / "never-created").exists()
