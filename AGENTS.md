# Repository instructions

These instructions apply to the complete repository. Read `README.md` and `docs/architecture.md` before changing behavior. `CLAUDE.md` points to this same source of instructions.

## Scope and layout

- `PatchToRepo.au3` is the single application entry point, including isolated native self-tests. Keep it at the root: compiler icon paths and the self-install workflow depend on this layout.
- `assets/` contains the icon, master artwork, and asset usage notes.
- `scripts/` owns shared build and verification behavior. The root CMD files are interactive launchers only.
- `tests/test_git_workflow.py` exercises real Git behavior in disposable repositories; it does not execute AutoIt.
- `tools/check_repository.py` checks public repository structure, links, version consistency, and binary icon integrity.
- `docs/` holds user, architecture, testing, development, and publication documentation.

## Required invariants

1. Apply only to a user-selected Git working tree. Preserve the index and commit history.
2. No automatic reset, stash, commit, fetch, push, reverse application, partial application, or ownership-check bypass.
3. Check and apply the same protected patch snapshot. Perform a fresh check for each Apply click.
4. Refuse bidirectional ambiguity and unsupported submodule-pointer changes.
5. Pass user paths directly to native process APIs with correct Windows argument quoting; never interpolate them into a command shell.
6. Keep immutable queued action inputs, one active picker, and busy-state protection around dialogs, setup, and Git operations.
7. Validate GUI control creation before entering the event loop. Zero is an idle GUI event, not a valid action.
8. Install per user, use the 64-bit registry view on x64, and preserve the user's default patch association.
9. Uninstall only the owned verb and shortcuts. Do not remove repositories, history, unexpected directories, or arbitrary user files.
10. Report persistence, capture, cleanup, and setup failures accurately. Keep warnings visible.

## Validation

Run `python tools/check_repository.py` and `python -m unittest discover -s tests -p "test_*.py" -v` for repository/Git changes. For AutoIt, build, setup, or Windows behavior, also run `scripts/Build.ps1` and `scripts/Verify.ps1 -IncludeCompiled` on Windows. See `docs/testing.md` for the manual acceptance gate.

Use disposable repositories and isolated test registry keys. Never run the application normally merely to inspect it: a no-argument launch installs integration. Use `--self-test` through the verification script for isolated checks.

Do not claim Windows, GUI, or compiled validation when only Python tests or static checks ran. Keep tool versions and SHA-256 pins explicit. Pin workflow actions to full commit IDs and keep repository permissions read-only unless a separate reviewed feature needs writes. Do not publish releases, push commits, or alter an external repository unless the user asks.

## Editing conventions

Use four-space indentation. Keep `.au3` UTF-8 with BOM and CRLF; keep Windows scripts CRLF. Update documentation alongside user-facing changes. Keep `VERSION`, native compiler metadata, wrapper metadata, changelog, and packaged versions consistent. Prefer focused changes over broad rewrites of the Windows boundary code.
