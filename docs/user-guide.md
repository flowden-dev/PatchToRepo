# User guide

## Everyday workflow

1. Right-click one `.patch` file in Explorer and choose **Apply patch to repository...**.
2. Choose a recent repository, paste its folder path, or use **Browse...**. For example: `C:\Projects\my-repository`.
3. Optionally use **Check only** to view compatibility and the file-change summary.
4. Click **Apply patch**. A fresh check runs before application, even after a successful Check only.
5. Review the diff in your Git application and commit when ready.

Selecting a subfolder resolves it to the repository root. The helper remembers up to 20 validated roots, most recently used first, and preselects the last one. It remembers the root after validating the repository, even if the patch subsequently fails to apply.

No GitHub account or token is needed for a local patch. A patch does not have to come from GitHub.

## Controls

| Control | Behavior |
| --- | --- |
| Recent repositories | Select a stored path or type a new path. |
| Browse... | Select the repository folder. |
| Forget path | Remove the selected path from history; files are untouched. |
| Check only | Validate and show a summary without changing working files. |
| Apply patch | Validate again and apply to the working tree. |
| Close after successful apply | Initially enabled. Success without warnings closes the picker after a message; warnings or a pending next patch keep it open. The checkbox is a per-window choice. |
| Choose patch... | Select a different patch; the dialog also accepts `.diff` files. |
| Open repo | Open the selected repository folder in Explorer. |
| Copy details | Copy the operation log for troubleshooting. |
| Install / repair | Refresh the context menu and shortcuts using the running helper. |
| Uninstall | Remove the menu and shortcuts; retain installed files and history. |
| Setup > Locate Git... | Select a custom or portable `git.exe`; its path is remembered. |

Only `.patch` receives an Explorer menu entry. Use Choose patch for `.diff` files. Multi-file context-menu application is not supported.

## Application behavior

The effective patch commands are:

```text
git -c apply.ignoreWhitespace=no apply --whitespace=warn --check -- PATCH
git -c apply.ignoreWhitespace=no apply --whitespace=nowarn --reverse --check -- PATCH
git -c apply.ignoreWhitespace=no apply --whitespace=warn --stat --summary -- PATCH
git -c apply.ignoreWhitespace=no apply --whitespace=warn --verbose -- PATCH
```

The helper passes the selected repository directly to Git and runs patch commands at the resolved repository root. It removes inherited Git routing variables that could redirect operations, while respecting normal repository configuration, attributes, and ownership checks. Other quiet/output flags are omitted from the illustration above.

- Changes remain unstaged and uncommitted. Existing staged entries and commit history are preserved.
- Unrelated local modifications may remain. Unresolved index conflicts block application.
- Text and Git binary patches, additions, deletions, renames, and linked worktrees are supported.
- A protected temporary patch copy ensures validation and application use the same bytes. Read-only source patches are supported.
- If the forward check fails but the reverse check succeeds, the patch **appears already applied**. That message is diagnostic; the tool does not undo it.
- If both checks succeed, the patch is ambiguous and is refused. Repeated text can otherwise cause a retry to modify a different matching block.
- Submodule-pointer patches are refused. Nonstandard patches needing custom stripping, forced whitespace matching, partial application, or three-way merging need a manual Git workflow.
- Email-style patches are treated as file changes. Authorship, commit messages, and individual commit boundaries are not imported.

Git's ordinary hunk conflicts reject the patch without partial hunk application. The helper does not guarantee transaction rollback for disk, permission, or concurrent filesystem errors during writing. Inspect the working tree if application fails after writing begins. Avoid concurrent edits while applying.

Whitespace warnings are shown without rewriting patch contents to fix them. A successful operation with warnings, truncated output, or unavailable capture stays open for review. Truncation preserves the valid UTF-8 prefix.

## Multiple invocations

An idle existing picker receives a newly selected patch rather than opening another window. While Git, a modal picker, or setup is active, another invocation asks you to finish the current action first.

A queued Check or Apply uses the patch and repository selected at the click. An accepted next patch is presented afterward and prevents automatic closing. Choosing a file explicitly in Choose patch supersedes an earlier pending handoff.

## Installation and removal

Running the helper with no arguments, or with `--install`, installs or repairs the integration and opens the picker. Run as your normal user.

| Item | Location |
| --- | --- |
| Installed helper | `%LOCALAPPDATA%\PatchToRepo\PatchToRepo.exe` or `PatchToRepo.au3` |
| Source-mode icon | `%LOCALAPPDATA%\PatchToRepo\assets\PatchToRepo.ico` |
| Settings/history | `HKEY_CURRENT_USER\Software\PatchToRepo` |
| Explorer verb | `HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\.patch\shell\PatchToRepo` |
| Shortcuts | Current user's Start menu, under **Patch to Repo** |

The application uses the 64-bit registry view on Windows x64. The normal default application for opening patches is preserved. Source installations require AutoIt to remain available at the registered interpreter path. Compiled installations need no AutoIt or external icon at runtime.

**Remove integration:** click Uninstall. The picker stays open so Install / repair can restore it immediately. The same actions are available in Setup. The Start menu removal shortcut also works after closing the existing picker.

**Complete removal:** uninstall integration, close the picker, then delete `%LOCALAPPDATA%\PatchToRepo` and the settings key above. These locations contain helper files and preferences, not repository data.

**Update:** close the old picker, then run the desired newer source or EXE with no arguments. Repository history is retained. Moving the downloaded folder does not break an installed menu. If AutoIt itself moves, run the desired source through its new interpreter to repair the registration. A running older source can install its own older copy again; use the intended version.

The source icon is copied to a stable installed location. If a source file is deliberately separated from its assets, basic operation remains available using the AutoIt icon. Close and reopen the Explorer context menu after refreshing integration.

## Command line

| Invocation | Result |
| --- | --- |
| `PatchToRepo.exe` | Install/repair and open the picker. |
| `PatchToRepo.exe --install` | Same interactive install/repair behavior. |
| `PatchToRepo.exe --apply "C:\Downloads\change.patch"` | Open the picker with that patch. |
| `PatchToRepo.exe "C:\Downloads\change.patch"` | Same patch-selection behavior. |
| `PatchToRepo.exe --uninstall` | Remove integration and shortcuts. Close an existing picker first. |

`--apply` selects a patch; it does not apply automatically or bypass repository selection. Source mode accepts the same arguments after the script filename. The development-only `--self-test` mode is documented separately in the source repository.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Menu missing | Run Install / repair, close the context menu, and reopen it on one `.patch` file. |
| Git missing | Use Setup > Locate Git; a common path is `C:\Program Files\Git\cmd\git.exe`. |
| Patch does not apply | Confirm the repository and starting revision. The helper cannot repair a patch for different source contents automatically. |
| Already-applied or ambiguous message | Inspect the current diff before retrying manually. Do not assume a successful reverse check proves the patch's history. |
| Dubious ownership | Read Git's ownership error and resolve it through your normal Git configuration. The tool does not bypass it. |
| Update fails | Close running copies and retry from a writable folder. Previous completed installed files are preserved after a failed staged replacement. |
| Source icon missing | Restore the complete assets folder, close the picker, and rerun the source to refresh integration. |

Use Copy details when reporting a problem, but remove private paths and repository contents first. The application has no automatic updater or telemetry. Normal exits remove temporary files; forcibly terminating it may leave a `PatchToRepo-*` directory in `%TEMP%`.
