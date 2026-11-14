# Contributing

Read [AGENTS.md](AGENTS.md) and the [architecture](docs/architecture.md). Keep
changes focused and document user-visible behavior.

Before a pull request, run Ruff, pytest and the package build. Add a small real
Git regression fixture for changes to patch application or safety. UI changes
should include a focused Qt test and visual inspection. Use disposable files;
never test against important repositories.

Describe the trigger, resulting behavior and validation. State Windows tests
that were not run. Do not attach private recovery bundles or source files to
public reports. Never add automatic commits, staging, resets or partial apply.
