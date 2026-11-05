# Testing and acceptance

## Automated checks

| Layer | Command or job | What it establishes |
| --- | --- | --- |
| Repository | `python tools/check_repository.py` | Required files, version metadata, local documentation links, workflow action pins, and ICO/PNG integrity |
| Git semantics | `python -m unittest discover -s tests -p "test_*.py" -v` | Git's patch behavior and the application's selected flags in disposable repositories |
| AutoIt syntax | `scripts/Build.ps1` or `scripts/Verify.ps1` | Native Au3Check with undeclared-variable and warning checks |
| Native application | `scripts/Verify.ps1 -IncludeCompiled` | Actual application self-tests in both source and compiled modes |
| Build output | `scripts/Build.ps1` | Successful compiler exit, x64 GUI PE header, version consistency, and staged output replacement |
| Manual acceptance | Procedure below | Interactive Explorer, display scaling, installation, update, and removal behavior on the target OS |

GitHub Actions runs the first five layers using Ubuntu 24.04 and Windows Server 2022 hosted runners. Windows CI is useful automation but does not replace manual acceptance on Windows 10 x64. Test logs are saved even after native test failure. Artifacts contain only completed builds from a successful verification path.

## Separate Git regression suite

The 20 tests cover read-only checks; working-tree application with unchanged index/history; already-applied diagnostics; wrong repositories; conflict rejection without partial hunk application; unrelated local edits; additions; binary changes; rename/delete/add patches; subfolders and linked worktrees; bare repositories; unmerged entries; path traversal; changes after an earlier check; CRLF checkouts; whitespace preservation; snapshot bytes; submodule no-op behavior; repeated-context reapplication; fresh bidirectional ambiguity; and ordinary end-of-file additions.

Some tests deliberately demonstrate raw Git accepting an unsafe retry or ignoring a submodule pointer. Those tests establish why the application's guards are needed; the native suite exercises the actual guards.

## Native self-tests

From a built checkout on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Verify.ps1 -IncludeCompiled
```

Both modes must exit zero and emit the exact `PATCHTOREPO_SELFTEST_PASS` line. A zero exit without that marker is a failure. Each attempt starts a new log under `build\test-logs` so an older success marker cannot satisfy a later attempt. Fatal errors use `/ErrorStdOut` so the runner can capture them.

Coverage includes Windows argument quoting, fast child exit status, long command lines, separate stderr, launch/capture failures, empty output, UTF-8 truncation, MRU ordering and persistence, read-only snapshots, staged updates, protected shortcut removal, isolated registration and shortcuts, hidden GUI initialization, window identity, busy/idle handoff, immutable queued actions, Unicode paths, warning-dependent auto-close, and the actual Git check/apply path. The source mode also checks a deliberate interpreter runtime failure.

The tests use `%TEMP%` directories and unique keys under `HKCU\Software\PatchToRepoSelfTest-*`. They do not intentionally write the production context menu, Start menu shortcuts, or repository history. A terminated test can leave its temporary directory or key. Do not run modified untrusted source merely because it accepts the test argument.

## Manual Windows acceptance

Use a disposable repository with a known compatible patch. Run on Windows 10 x64 as a normal user.

1. Close the old picker. Run the new EXE once and confirm the context-menu entry and Start menu shortcuts appear with the custom icon. Verify the extension's normal Open action is preserved.
2. Right-click the patch, select a repository, and use Check only. Confirm no working file, index entry, or commit changed. Apply, inspect the resulting diff, and confirm the index/history remain unchanged.
3. Open the picker again and confirm the recent root is remembered and preselected. Check typed paths, trailing separators, spaces, umlauts, a subfolder, and a linked worktree.
4. Repeat an already-applied patch and use an incompatible patch. Confirm clear errors and unchanged files. Try a patch with repeated context and verify ambiguous retries are refused.
5. Try mouse clicks, Enter on the default button, cancellation, and file/folder dialogs. While busy, another invocation must not replace current inputs. A newly acknowledged next patch must survive auto-close.
6. Click Uninstall and verify the Explorer entry and both shortcuts disappear. Click Install / repair and verify they return. Confirm setup controls are disabled during operations.
7. Close the picker, install an updated copy, and verify the registered stable path. Move the downloaded folder and confirm the installed menu still works. Repeat with uncompiled source, including its installed ICO.
8. Test the EXE without any external assets or AutoIt installed, with Git available. Inspect the embedded icon in Explorer, the title bar, and shortcuts at 100%, 125%, 150%, and 200% scaling as available.
9. Check successful application with warnings, Git-not-found handling, and a normal read-only patch. Review logs before retrying any write-phase failure.
10. Remove integration, close the helper, and follow complete-removal instructions. Confirm no repository data was deleted.

Record Windows build, display scaling, AutoIt/Git versions, commit, and results in the release record.

## Initial repository status

Preparation validation on 2026-11-05 used Python 3.12.14, Git 2.52.0, and PowerShell 7.6.9 on Linux. Repository/link/version/icon checks passed, all 20 Git tests passed, and the PowerShell scripts parsed successfully. Shared PowerShell version reading, argument quoting, and separate stdout/stderr process capture were exercised on Linux. All GitHub YAML files parsed, actionlint 1.7.12 accepted the workflow, and a clean Git import passed whitespace and generated-file exclusion checks. The application source and ICO remain byte-identical to the imported 1.0.4 snapshot.

Native AutoIt, Explorer, Windows sharing behavior, Windows PowerShell 5.1 execution, and EXE compilation could not be executed during repository preparation. The GitHub workflow is supplied but has not run on GitHub yet. The repository provides a repeatable Windows verification path and keeps those native checks as release requirements. Do not turn an unexecuted workflow into a claimed passing result.
