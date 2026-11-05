# Changelog

Changes follow semantic versioning. Entries below describe the delivered application snapshots; they do not imply that Git tags or GitHub releases already exist.

## Unreleased

### Added

- Public repository documentation, an MIT license, contribution and security guidance, issue forms, and pull request guidance.
- Shared PowerShell build, verification, toolchain setup, and release packaging scripts.
- GitHub Actions for repository checks, Git integration tests, native Windows tests, and downloadable build artifacts.
- SHA-pinned action dependencies, checksum-verified AutoIt setup, and Dependabot configuration.
- Repository instructions in `AGENTS.md` and `CLAUDE.md`.

## 1.0.4

### Added

- Custom transparent icon in nine sizes from 16 to 256 pixels.
- Embedded EXE icon, picker icon, stable source-install icon, and shortcut icons.
- Native compiler and SciTE wrapper icon settings and a convenient compile launcher.

## 1.0.3

### Added

- Visible Install / repair and Uninstall buttons using the existing setup handlers.

## 1.0.2

### Fixed

- Reapplication at a second matching block when both forward and reverse checks succeed.
- Incoming patches overtaking queued Check or Apply actions.
- Incoming patch handoff during modal dialogs and setup actions.
- Output read failures being mistaken for valid Git output; warnings and truncated UTF-8 output handling.
- Native verification now requires a successful exit and an explicit completion marker.

## 1.0.1

### Fixed

- Incomplete GUI creation dispatching actions through zero control IDs.
- Read-only snapshot cleanup and interrupted installed-file replacement.
- Single-instance handoff races and window identity checks.
- Shortcut removal refusing directories, and shortcut creation errors being reported.
- Patch inspection I/O failures, MRU normalization and persistence errors, and clipboard errors.

## 1.0.0

### Added

- Per-user patch context menu, recent repository selection, check and apply workflows, and source or compiled operation.
