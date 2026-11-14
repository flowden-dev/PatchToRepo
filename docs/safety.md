# Safety and supported inputs

The application uses Git's own patch parser and working-tree apply engine.
It checks forward and reverse applicability and compares Git's NUL-delimited
file inventory with its own conservative review inventory. A check succeeds only
when the forward operation works and the reverse operation does not.

Patches apply as complete units. No `--reject`, `--3way`, `--unsafe-paths`,
whitespace fixing, staging or automatic commits are used. Git ownership checks
remain enabled. Inherited `GIT_*` routing/configuration variables are removed;
Git is launched directly without a shell. Local repository configuration remains
in effect, with strict whitespace matching and optional Git locks/fsmonitor
disabled explicitly for the read/review workflow. Automatic lazy object fetching
is disabled. External content filters are refused, not executed.

## Supported

- Git-format unified diffs with default `a/` and `b/` prefixes
- Single `git format-patch` messages (commit metadata is not applied)
- Text, Git binary literal/delta payloads, additions, deletions, ordinary renames/copies
- Spaces and UTF-8 filenames, byte-preserving legacy text contents, missing final newlines
- Normal repositories, unborn branches and linked worktrees
- Local modifications when ordinary Git application remains unambiguous

The preview uses the same Git directory/configuration and an explicitly isolated
working tree containing affected files and ancestor `.gitattributes` files.
Relative `core.attributesFile` paths retain their original location. EOL,
`working-tree-encoding` and `ident` conversion follows Git in both preview and
Apply; the preview therefore shows the actual converted working-file bytes.
Git may still refuse incompatible input; the tool never enables whitespace-ignore
or manual line-ending repair. A patch that changes attributes follows Git's
normal attribute-loading order, including its cached rules for that operation.
Mode changes are accepted when the whole patch is unambiguous; pure mode-only
patches that pass both check directions are refused.

## Explicitly refused

Combined merge diffs, traditional non-Git patches, zero-context patches requiring
`--unidiff-zero`, custom path stripping, nested repository traversal, submodule
pointer changes, symlinks/junctions, affected hard links, special file modes,
sparse checkouts, case-only renames, repeated or overlapping paths across file
blocks, file/directory replacements, Windows-reserved filenames and unsafe paths.
Affected paths with external Git filters, including LFS, are refused. Known filter
commands are also disabled during the isolated trial, then the resulting attributes
are checked to reject filters introduced by the patch itself. Filter driver names
that collide with Git's `unset`/`unspecified` output are handled conservatively.
The index is checked for submodule and symlink boundaries even if their working
directories/files have been removed or replaced. Unrelated indexed submodules
and symlinks do not prevent patches to ordinary files.
A multi-commit series touching the same file must be exported as one cumulative
diff. Binary `files differ` messages without actual patch data are not applicable.

These are explicit scope limits. Unsupported inputs receive an error; they are
not skipped, partially applied or silently converted.

## Resource limits

| Resource | Limit |
| --- | --- |
| Patch bytes | 32 MiB |
| File changes | 2,000 |
| Saved repositories / simultaneous probes | 50 / 4 |
| Individual affected file | 32 MiB |
| Affected file bytes per snapshot | 256 MiB |
| Expanded binary payload sizes per patch | 256 MiB across both directions |
| Side-by-side text | 2 MiB per side; 20,000 lines; 10,000 characters per line |
| Syntax coloring | 512 KiB of decoded text per side |
| Raw source preview | 2 MiB (larger input is visibly marked as truncated) |
| Draft editing | 512 KiB, UTF-8 with LF; text must round-trip through the editor |
| Cached comparisons | 8 files/encoding combinations |
| Git captured output | 8 MiB per stream |
| Git index inventory | 64 MiB stdout; staged modes checked without reading tracked file contents |
| Check/read command / apply process timeout | 45 / 120 seconds |
| Incoming Explorer queue | 20 patches |

Limit checks protect normal desktop responsiveness. Git's compressed binary
payload framing, bounded zlib expansion and delta result sizes are validated
before Git sees them. No sandbox should be inferred for arbitrary local Git
configuration or for every possible resource-exhaustion input. Use trusted Git
installations and repositories.

## Concurrency and failure

Snapshots are immutable bytes. Review and Apply compare affected file content and
modes, HEAD, branch, repository location, index/configuration digests and effective
attributes. The engine rechecks
again after saving recovery data, immediately before invoking Git.
The UI separately verifies the selected repository matches the review's root,
including when Apply is invoked through a shortcut. Changing repositories during
draft editing discards the old review while preserving the draft itself.

An OS-held application lock coordinates this app's processes. It does not lock
external editors or all other Git clients. The unavoidable final race with an
external writer, process termination and storage failure means an absolute
transaction/zero-conflict guarantee would be misleading. A final mismatch is
reported and recovery copies remain available; the tool never automatically
rolls back over newer edits.

A successful apply is verified against the preview and repository identity/index.
This verifies the expected working-file transformation, not program correctness.
