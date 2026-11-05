<img src="assets/PatchToRepo.png" alt="Patch to Repo icon" width="96">

# Patch to Repo

**Apply a `.patch` file to a local Git repository from the Windows context menu.**

Right-click a patch, select a recent repository, and apply. Patch to Repo remembers your repository folders and checks compatibility before changing working files.

[User guide](docs/user-guide.md) · [Build from source](docs/development.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## Features

- Explorer context-menu integration for `.patch` files, installed for your Windows account.
- Up to 20 recent repositories, with the last repository preselected.
- **Check only** for a compatibility check and change summary.
- Fresh validation on every **Apply patch** operation.
- Changes left unstaged and uncommitted for review in your preferred Git application.
- Visible **Install / repair** and **Uninstall** buttons.
- One picker window, with subsequent patch files handed to it when idle.
- A custom icon for the application, context menu, and Start menu shortcuts.

## Requirements

| Use | Requirements |
| --- | --- |
| Compiled application | Windows 10 x64 and Git for Windows |
| Run the source | The above, plus AutoIt 3.3.16.1 or newer |
| Build or run native tests | AutoIt, Git for Windows, and Windows PowerShell 5.1 or PowerShell 7 |
| Run separate Git regression tests | Python 3.10 or newer and Git; no Python packages required |

Windows 10 x64 is the target platform. Other Windows versions have not been accepted as supported targets yet. The Python Git tests also run on Linux; the application itself is Windows-only.

## Get started

### Use a compiled release

If a compiled release is available on this repository's **Releases** page:

1. Download and extract the Windows x64 ZIP.
2. Run **PatchToRepo.exe** as your normal user. It installs the menu and opens the picker.
3. Right-click a `.patch` file, choose **Apply patch to repository...**, select a repository, and click **Apply patch**.
4. Review the changed files and commit them in your usual Git application.

Administrator rights and a GitHub account are not required. Install [Git for Windows](https://gitforwindows.org/) first if needed. Existing default applications for opening patch files are preserved.

### Build your own EXE

1. Download or clone this repository and install [AutoIt](https://www.autoitscript.com/site/autoit/downloads/).
2. Double-click **Compile-Windows.cmd**. The EXE is written to **build\PatchToRepo.exe** with the icon embedded.
3. Double-click **Verify-Windows.cmd** to run the source and compiled native self-tests.
4. Close any old picker, then run the new EXE once.

You can also run **PatchToRepo.au3** using AutoIt without compiling. Keep the `assets` folder beside the source for the custom icon. [Portable toolchains and command-line builds](docs/development.md) are supported too.

## What changes

The helper uses `git apply` on your working files. It does not create commits, stage files, push, fetch, reset, stash, or change Git configuration. Unrelated local edits can remain present. A repository with unresolved index conflicts is refused.

The checked patch is held in a protected temporary copy until the operation finishes. Forward and reverse checks detect incompatible, apparently already-applied, or ambiguous patches. Text and Git binary patches, file additions, deletions, renames, and linked worktrees are supported. Patches that change submodule pointers are refused.

Normal hunk conflicts reject the patch without partial hunk application. Disk errors or another program editing the same files can still require manual inspection. See the [application behavior and limitations](docs/user-guide.md#application-behavior).

## Uninstall or update

Click **Uninstall** in the picker to remove the context menu and shortcuts. Repository history and the installed helper are kept for convenient reinstallation. Click **Install / repair** to restore the integration.

To update, close the old picker and run the newer source or EXE with no arguments. The helper uses a stable copy under `%LOCALAPPDATA%\PatchToRepo`; moving the downloaded package does not break the menu. [Complete removal and stored settings](docs/user-guide.md#installation-and-removal) are documented in the user guide.

## Development and validation

GitHub Actions is configured to run the Git regression suite on Linux and build and test both source and compiled modes on Windows. It produces a Windows ZIP and SHA-256 checksum as build artifacts. Workflows use pinned action commits, a checksum-verified AutoIt download, and read-only repository permissions.

**Validation status:** repository checks and the separate Git tests can be run outside Windows. Native AutoIt, Explorer interaction, and the compiled release require Windows verification. The first public binary should be published after the workflow and the [manual acceptance checks](docs/testing.md#manual-windows-acceptance) pass. No passing CI badge or native test result is claimed in this initial snapshot.

- [Architecture and function map](docs/architecture.md)
- [Testing and acceptance](docs/testing.md)
- [Publishing and release procedure](docs/publishing.md)
- [Security policy](SECURITY.md)

## License and credits

Project source, documentation, and included artwork are provided under the [MIT license](LICENSE). AutoIt and Git are separate upstream projects; see [third-party notices](THIRD_PARTY_NOTICES.md). [Credits](CREDITS.md) records the project and upstream acknowledgments.
