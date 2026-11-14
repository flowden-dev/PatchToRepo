# Repository instructions

Read README.md and docs/architecture.md before changing behavior. CLAUDE.md
points here. Keep the engine independent of Qt and test it with real disposable
Git repositories. Match four-space Python formatting and lowercase comments.

Required invariants:
- Never stage, commit, reset, stash, fetch, push, partially apply or auto-reverse
- Compare the exact immutable patch and before/after files the user reviewed
- Never apply after stale review, failed checks or unresolved ambiguity
- Bind Apply to the selected repository; invalidate review on every target change
- Respect indexed symlink/submodule boundaries even when absent from the working tree
- No shell command interpolation, unsafe paths or safe.directory bypass
- Keep UI jobs immutable; ignore stale results and block apply during edits/jobs
- Preserve bytes, index and unrelated files; save recovery data before writes
- Settings and recovery failures must remain visible
- Commit related preferences together, close connections promptly, then update the UI
- Explorer integration is per user and preserves the default file association
- No network calls during normal application use

Run `python -m ruff check .`, `python -m ruff format --check .`, and
`python -m pytest -q`. Use `QT_QPA_PLATFORM=offscreen` on headless systems.
Build with `python -m build`. Windows integration must be tested on Windows;
never claim Linux mocks prove Explorer behavior. Update docs for changed limits
or safety semantics. Pin CI actions to complete commit IDs. No automatic
commits or publishing. Only ChatGPT and Claude agent instruction files belong
in this repository.
