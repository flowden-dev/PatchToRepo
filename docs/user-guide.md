# User guide

## Open and select

Use Explorer's **Review and apply patch…**, drag one local file onto the window,
or press **Ctrl+O**. Opening a patch never applies it. A second Explorer request
is queued behind the active review; use **Open next** when ready.

Click **Add…** and choose a repository folder. Subfolders are resolved to the Git
working-tree root. Repositories are retained between launches. On first launch,
the previous AutoIt tool's `RecentRepos` and `GitExe` settings are imported from
`HKCU\Software\PatchToRepo` without deleting those registry values.

**Find match** runs real Git checks against saved repositories, at most four at
once. A unique successful candidate is preselected. A patch that only adds new
files may fit several repositories; choose the intended one. Filenames and
existing paths cannot prove which repository a patch belongs to.

## Review

The left pane is the current working file; the right pane is the result of
applying the patch in a temporary directory. Uncommitted changes in affected
files are included. Red marks removed lines, green marks added lines, stronger
shading marks changed characters. Blank alignment rows have no line number.

- Select files on the left; filter by any part of their path
- **F8 / Shift+F8** moves between change blocks in the selected file
- **Ctrl+F**, enter a search term, then **Enter** searches the last focused code pane
  and wraps; if absent there, it searches the other pane, including deleted code
- Horizontal and vertical scrolling are linked; lines deliberately do not wrap
- Each vertical scrollbar includes markers showing changes throughout the file
- Click a colored marker to jump both panes to that block; hover for its line counts
- Drag the thumb to scroll normally; its left edge stays clear of clickable markers
- Click or drag the track outside the thumb to move directly through the file
- With a map focused, **Up/Down** selects changes and **Home/End** goes to the file ends
- Change code size in **Settings**; display encoding is selectable above the panes
- Use **Patch source** for the original unified patch and **Diagnostics** for Git's output

Each map has a red lane for removed lines and a green lane for added lines.
The scrollbar thumb shows the currently visible portion. Both maps use aligned
comparison rows, including blank alignment gaps, so the positions match across
the two panes. Tiny changes retain a visible minimum marker height. When several
changes overlap at one screen pixel, use **F8 / Shift+F8** to visit each one.

Red **−7** means seven removed patch lines; green **+80** means eighty added
patch lines. The comparison toolbar groups the previous/next arrows, current/total
change blocks, and red/green count badges. Counts also appear in the file list
and patch summary. Map tooltips count the highlighted before/after
lines in that block. Counts from the patch can differ from displayed blocks
when changes only affect line endings or display encoding hides a byte change;
the metadata note and Patch source remain authoritative for those cases.

Binary changes are labelled **binary**, without invented text-line counts.
Large/limited previews show **Metadata preview**, keep available patch counts,
and disable change navigation and location markers.
The map is also cleared when the preview is invalidated or another file loads.

The number of opened files is a navigation aid, not proof of review. The review
checkbox is your explicit acknowledgment. You may review the complete raw patch
instead of opening every file. Binary files and files beyond display limits
show byte counts and SHA-256 hashes; their contents are not presented as text.

A new check, repository change or patch edit clears the acknowledgment. Apply
requires a successful current review. Existing index conflicts, active
merge/rebase operations and unsafe/unsupported inputs block application.
Changing repositories while a draft is being edited clears the old comparison.
Check the edited draft, or discard the edits and run **Check again** before Apply.

## Edit a patch draft

In **Patch source**, select **Edit draft**. Editing is available for UTF-8 patches
with LF line endings up to 512 KiB. Other patches remain usable for review and
application without conversion.

Control and formatting characters that would distort the comparison are shown as
`⟦U+…⟧` labels. Their original bytes are retained. Such patch sources remain
read-only when Qt cannot represent them faithfully as editable plain text.

Edit the unified diff and keep hunk line counts valid. Choose **Check edited
draft** to parse it, repeat repository detection and rebuild the preview. The
application does not silently repair malformed hunks or normalize repository
files. The downloaded original stays unchanged. **Discard edits** restores the
loaded snapshot; **Save copy…** exports the loaded or currently edited bytes.

Saving a copy does not certify that unchecked edits are valid. A later program
changing the original patch file does not change the already loaded snapshot;
reopen the file to load new bytes.

## Apply

Tick **I have reviewed the changes**, then choose **Apply patch** or **Ctrl+Enter**.
The program repeats validation, compares repository state and file bytes, saves
a recovery ZIP, applies the same byte string through Git, and verifies the result.

The index and commits are not modified. Added files remain untracked; use your
usual Git client to inspect, stage and commit later. Unrelated local work is
retained. Git errors and warnings remain available in **Diagnostics**.

Previews use the repository's Git line-ending and encoding rules. Both the
before and after panes describe the actual working-file bytes. Files using
external filters (including Git LFS) require manual handling and are refused;
the app does not run those filter commands or download their content.

When a conflict occurs, verify the repository and patch base. Obtain a patch
for your current source revision or resolve the discrepancy in your editor.
There is no partial-apply or force button. Textual compatibility does not verify
that code compiles or behaves correctly.

## Recovery copies

Before every write, the app saves a ZIP under
`%LOCALAPPDATA%\PatchToRepo\backups`. Use **Recovery copies** to open that folder.

Each ZIP contains:

| Entry | Meaning |
| --- | --- |
| `reviewed.patch` | Exact bytes that were checked and submitted to Git |
| `manifest.json` | Repository path, per-file before/after hashes, modes and backup mapping |
| `before/000000.bin`, etc. | Original bytes, including local edits, for existing affected files |

A `before_sha256` of `null` means that path did not exist. An `after_sha256` of
`null` means the patch deletes that path. The numbered entries avoid unsafe
archive filenames. Use the manifest to map each entry back to its repository file.

For manual recovery, first preserve any edits made since application. Compare
the current files with the manifest's after hashes, then copy the needed original
entries back to their named paths. Newly created paths have no original copy;
remove one only after confirming it contains no later work. Do not blindly reset
an entire repository. No automatic restoration is offered because it could erase
later edits.

The bundle proves what was prepared, not that Git completed successfully. A
failure can occur after a bundle is saved. Disk errors, termination or an
external editor writing during the final apply require manual inspection.
Recovery ZIPs are retained until you delete them and may contain private source.

## Updating and removing

Close the app, then rerun **Setup-Windows.cmd** from a newer source checkout.
The stable Python environment and preferences remain in your user profile.
When using a compiled application, open the new build and use **Settings →
Install / repair menu**. Versioned application copies avoid overwriting a running
EXE. Do not reopen the old AutoIt tool: it may reinstall its old Explorer command.

**Remove menu** removes the owned `.patch`/`.diff`/`.mpatch` verbs and the two
named Start menu shortcuts. It leaves default file associations untouched.
For complete removal, close every instance after removing the menu and delete
`%LOCALAPPDATA%\PatchToRepo` only after keeping any recovery copies you need.
Older installed application copies can be removed from its `applications` folder
after installing the new menu and confirming it launches correctly.

Settings are saved together. If saving fails, the previous live settings and
review remain active and the error stays visible; no success message is shown.

The database is `preferences.sqlite3`. `application.log` rotates at 1 MiB with
two older files. Linux uses `$XDG_DATA_HOME/patch-to-repo` or
`~/.local/share/patch-to-repo`; Explorer integration is Windows-only.

## Fast review workflow

The review confirmation is directly beside **Apply patch**. Confirm the review,
then click Apply (or press Tab, then Space; Ctrl+Enter also applies).
**Close after apply** sits immediately below the confirmation and remembers
your choice across launches. Change it here whenever your workflow changes;
no Settings dialog is needed. It defaults to off.

Automatic closing requires verified success. Errors, verification mismatches
and queued patches keep the window open. The option is disabled while an
operation is running. If the preference cannot be saved, its previous value
is restored and the error is shown. Recovery copies are still saved before
applying, including when automatic closing is enabled.
