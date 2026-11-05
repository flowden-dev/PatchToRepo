# Patch to Repo

Apply `.patch` files to local Git repositories from the Windows context menu.

## Install

1. Use Windows 10 x64 and install [Git for Windows](https://gitforwindows.org/).
2. Extract this archive and run **PatchToRepo.exe** as your normal user.
3. Right-click a `.patch` file and choose **Apply patch to repository...**.
4. Select a repository, click **Apply patch**, and review the changed files.

AutoIt is not required for this compiled build. No administrator rights or GitHub credentials are needed. The icon is embedded in the EXE.

Changes remain unstaged and uncommitted. Use **Check only** for a compatibility check without changing working files. The most recent repository is preselected next time.

## Update or remove

Close the old picker, then run the newer EXE once to update. The installed helper lives under `%LOCALAPPDATA%\PatchToRepo`, so moving the downloaded archive does not break the menu.

The visible **Uninstall** button removes integration and shortcuts while retaining recent repositories. **Install / repair** restores integration. See the [user guide](docs/user-guide.md#installation-and-removal) for complete removal.

## Help and license

Read the [user guide](docs/user-guide.md) for limitations, error messages, and stored settings. The included [MIT license](LICENSE) covers project code and artwork; [third-party notices](THIRD_PARTY_NOTICES.md) identify the external tools. This release does not bundle Git.

This binary is unsigned unless the release publisher explicitly documents signing. Verify its accompanying SHA-256 checksum against the published release value before running it. Windows may show an unknown-publisher prompt for unsigned downloaded software.
