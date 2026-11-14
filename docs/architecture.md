# Architecture

Python provides the patch workflow, Qt Widgets the desktop interface, and Pygments
the syntax highlighting. The Git engine is independent of the UI.

## Review lifecycle

1. Read a bounded immutable patch byte string. Validate every path and compare
   the parsed file inventory with Git's NUL-delimited inventory.
2. Inspect saved repositories in a bounded background pool. Only a unique
   compatible repository is automatically selected; ties require a choice.
3. Check forward and reverse applicability. Reject existing conflicts, unsafe
   paths, unsupported file kinds, repeated paths and ambiguous application.
   Inspect staged modes as well as the filesystem to reject traversal into
   uninitialized submodules or missing/replaced indexed symlinks.
4. Snapshot affected working files and the ancestor attributes files they need.
   Point Git at an isolated temporary working tree while retaining its original
   read-only repository context, so EOL/encoding rules match actual application.
   Refuse external filters before checks and after the trial; suppress known
   filter commands during trial writes, including filters introduced by the patch.
5. Display aligned code panes, syntax, intraline changes and metadata. A patch
   draft edit invalidates previous review and requires another check.
6. On Apply, take an application lock, repeat validation and compare the fresh
   repository identity, index/configuration, effective attributes and affected
   file bytes with the reviewed state.
   The UI also requires the selected repository to equal the reviewed root;
   every target change invalidates the preview, including while editing a draft.
7. Save a recovery bundle before invoking Git. Apply without staging or commits;
   verify output bytes and preserve diagnostic details, including I/O failures.

## Boundaries

| Module | Responsibility |
| --- | --- |
| `patch.py` | Immutable patch, strict paths, supported format inventory |
| `git.py` | Shell-free Git processes, environment, discovery, timeouts |
| `engine.py` | Checks, sandbox preview, repository detection, guarded apply |
| `storage.py` | SQLite preferences/history, legacy import, recovery data |
| `integration.py` | Per-user Explorer verb, quoting and removal |
| `diff.py` | Bounded diff alignment and syntax spans |
| `widgets.py` | Code editor, gutters, synchronized diff panes |
| `overview.py` | Integrated change scrollbars, cached markers and count rendering |
| `window.py` | Background jobs, review state, actions and feedback |
| `app.py` | Arguments, startup, styling and single-instance handoff |

Preference connections commit or roll back within a scope and close immediately.
Related settings are committed together; live UI settings change only after the
transaction succeeds. Failures remain visible in the status banner/diagnostics.

## Safety contract

No reset, stash, commit, push, fetch, staging, partial apply, automatic reversal,
whitespace repair, permissive ownership override or three-way fallback. Git is
responsible for hunk semantics. The Python parser is an additional inventory
and path-safety gate, never a replacement patch engine. Original patch bytes
are passed on stdin, so replacing the downloaded file cannot change a review.

Display encoding never changes application bytes. Git's configured working-file
conversions are reflected in the before/after byte snapshots; no extra Python
normalization is applied to working files.
Git-format patches (including one format-patch email), binary patches, additions,
deletions and ordinary renames/copies are supported. Unsupported input is
refused explicitly; see the user guide for limits. A clean Git check establishes
textual compatibility, not whether new program behavior is correct.

The application lock coordinates this program's instances; it cannot lock an
IDE or every external Git client. Revalidation narrows the external edit race,
post-apply verification detects discrepancies, and recovery copies preserve the
pre-apply files. A disk failure or an external edit during Git's final write
cannot be made fully transactional by a desktop wrapper. No automatic rollback
is attempted because that could overwrite a newer external edit.

## Efficiency

Read touched files and their attribute inputs, not entire repositories. Scan at most four saved repos
at once, move Git and diff work off the UI thread, cache the current file's
render data, bound patch/file/output sizes, and cap expensive alignment and
syntax work. File lists and editors remain native Qt controls; no embedded web
runtime or remote service is required.

Diff scrolling uses a reentrancy guard around synchronization, not signal
blocking on Qt scrollbars. Qt's own viewport scroll and repaint notifications
must run for both horizontal and vertical movement. Clamping the shorter pane
does not feed its value back into the longer pane.

The footer close preference is persisted immediately and rolls back on save
failure. Deferred automatic close runs only following verified application
and checks for pending work/queued patches before closing.

## Change overview and counts

`overview.py` derives immutable marker runs and change blocks from the aligned
Rendered lines. Gap rows never add to line counts. Both editors share one map
model; each caches and deduplicates its pixel rectangles until the file or rail
size changes. The overview subclasses QScrollBar and replaces each editor's
vertical scrollbar. Qt retains native thumb dragging and wheel handling; markers
are painted over the native track/handle. A clear strip on the thumb's left edge
allows dragging even when a marker overlaps it. Style geometry is queried once
per paint/hit-test pass, not for every marker. Scrolling reuses cached rectangles.

Marker/track navigation reuses DiffView's synchronized jump path while preserving
horizontal positions. Wheel events must not be forwarded back to the viewport:
QAbstractScrollArea already forwards them to its scrollbar. Both horizontal
scrollbars reserve equal height so unequal line widths cannot misalign the panes.

Toolbar badges and file-list counts come from the validated patch inventory. Marker
tooltips describe the visible comparison, which can differ for byte-only/EOL
changes. Limited previews do not fabricate locations. A delegate paints two
count colors without allocating widgets per file; ordinary cell text remains
available for accessibility. Overview controls expose accessible names and
keyboard navigation.
