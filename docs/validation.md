# Validation

This record describes local checks for version **2.0.7** on **2026-11-14**.
It does not represent a hosted CI run or native Windows acceptance.

| Check | Result |
| --- | --- |
| Environment | Python 3.12.14, Git 2.52.0, PySide6 6.8.3; Linux x86_64 |
| Regression suite | 191 passed; 3 skipped |
| Ruff lint and formatting | Passed |
| Source distribution and wheel | Built successfully |
| Application smoke test | Passed against a disposable Git repository |
| Screenshot | Generated from the actual Qt application using a synthetic notes utility |

The skipped cases require native Windows registry/shortcut or command-line
behavior, or Unix-domain sockets unavailable in this execution sandbox.
They remain enabled in CI where supported.

The suite covers real Git application, index/history preservation, repository
selection, local edits, stale reviews, unsafe paths, attributes and encoding,
binary patches, recovery failures, draft editing, scroll synchronization,
change navigation, and close-after-apply behavior.

Windows executable, Explorer, and DPI behavior still require the
[manual Windows acceptance checks](development.md#manual-windows-acceptance).
