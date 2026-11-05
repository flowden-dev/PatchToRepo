# Development

## Toolchain

Use Windows x64, Git for Windows, and AutoIt 3.3.16.1 or newer. CI pins AutoIt **3.3.18.0** in [autoit-toolchain.json](../tools/autoit-toolchain.json). Build scripts run with Windows PowerShell 5.1 or PowerShell 7 and require no PowerShell modules from a package registry.

The application stays at the repository root so its compiler-relative asset paths and self-install behavior remain consistent. It uses only standard AutoIt includes. No SDK or compiler binaries are committed.

## Build

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Verify.ps1 -IncludeCompiled
```

The interactive **Compile-Windows.cmd** and **Verify-Windows.cmd** launch the same scripts and pause so results remain visible. Build first: the interactive verification launcher tests both the source and `build\PatchToRepo.exe`.

For a portable installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Build.ps1 -AutoItDir "C:\Tools\AutoIt\install"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Verify.ps1 -AutoItDir "C:\Tools\AutoIt\install" -IncludeCompiled
```

Alternatively set `AUTOIT_HOME` to the folder containing `AutoIt3_x64.exe`, `Au3Check.exe`, and `Aut2Exe`. An explicit `-AutoItDir` takes precedence. An explicit path or environment override is authoritative: incomplete overrides fail instead of silently selecting a different installation.

To download the pinned portable toolchain:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Setup-AutoIt.ps1
```

The setup script verifies the archive SHA-256 before extracting or running downloaded executables and installs under `.tools\autoit\install`. That path is discovered automatically when a standard installation is absent. Setup refuses an existing destination; reuse its install folder or choose a new `-Destination`. Updating the pin requires independently checking the official download and its version, then rerunning native tests.

Build runs Au3Check with undeclared-variable and warning checks, compiles to a unique staged path, validates the x64 PE GUI header and file version, and replaces `build\PatchToRepo.exe` only after success. A running or locked output causes an error; close it and retry. The custom ICO is passed explicitly and embedded. No UPX packing is requested.

## Tests

```text
python tools/check_repository.py
python -m unittest discover -s tests -p "test_*.py" -v
```

Python checks need Python 3.10+ and Git, with no pip dependencies. The same Git tests run in Linux CI. Native verification checks both exit status and the exact completion marker and writes logs to `build\test-logs`.

See [testing](testing.md) for actual coverage and manual acceptance. Use `--self-test` for isolated application tests; launching the application normally installs integration for the current user.

## Package

After building and verifying:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Package.ps1
```

Output is `dist\PatchToRepo-1.0.4-win-x64.zip` and its `.sha256` file, using the current `VERSION` value. The runtime archive contains the EXE, a runtime README, user guide, MIT license, and third-party notices. Source distributions are the repository itself. Git and the development toolchain are not bundled.

Packaging validates the executable architecture and version, but does not rerun tests or certify a manual Explorer check. The CI workflow runs verification before packaging. For public releases, follow the [publication gate](publishing.md#release-a-binary).

## Versioning and editing

`VERSION` stores the three-part application version. AutoIt native FileVersion/ProductVersion and wrapper Fileversion use the same value with `.0` appended. Update these together with the changelog for an application release. Repository scaffolding is recorded under Unreleased without changing runtime behavior.

Keep `.au3` UTF-8 with BOM and CRLF; keep CMD and PowerShell files CRLF. Use four spaces for application and script indentation, two for YAML/JSON. Do not commit `build`, `dist`, `.tools`, interpreter downloads, logs, or local editor state.

Manual Aut2Exe compilation is supported: select the source, `assets\PatchToRepo.ico`, x64, and GUI mode. Native `#pragma compile` and SciTE wrapper metadata are included; the checked build script is the preferred route because it also runs syntax and output checks.
