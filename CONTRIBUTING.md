# Contributing

Start with the [architecture](docs/architecture.md) and [development guide](docs/development.md). For bugs, use the issue form with a minimal reproduction, tool version, Windows/Git/AutoIt versions, and sanitized logs. Keep patches and repository data small enough to share safely.

## Changes

Use a focused branch and explain the user-visible problem in the pull request. Keep unrelated refactors separate. Follow `.editorconfig`, preserve the single-file application layout, and update the changelog and relevant documentation when behavior changes.

Patch to Repo intentionally leaves staging, commits, network operations, and complex conflict resolution to the user's Git application. Discuss features that expand this scope before implementing them.

## Checks

```text
python tools/check_repository.py
python -m unittest discover -s tests -p "test_*.py" -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Verify.ps1 -IncludeCompiled
```

Use disposable repositories for tests. `--self-test` uses temporary files and an isolated registry key; a normal no-argument application launch installs the real integration. Never test against another person's working tree without their authorization.

For Windows changes, report the native tests and relevant [manual checks](docs/testing.md#manual-windows-acceptance). If your environment cannot run them, say so; a Python-only pass does not validate the Windows implementation.

Keep discussions respectful and technical. Do not include credentials, proprietary patches, or personal filesystem paths. Report vulnerabilities through the [security policy](SECURITY.md). Contributions are submitted under this repository's [MIT license](LICENSE); no separate contributor agreement is required.
