# Third-party notices

The repository does not vendor AutoIt, Git, Python, GitHub Actions implementations, or their installers. Downloaded development tools live in the ignored `.tools` directory.

| Component | Role | Upstream terms |
| --- | --- | --- |
| AutoIt | Source interpreter, standard includes, and executable compiler | [AutoIt license](https://www.autoitscript.com/autoit3/docs/license.htm) |
| Git / Git for Windows | External executable used to validate and apply patches | [Git copying terms](https://github.com/git/git/blob/master/COPYING), [Git for Windows](https://gitforwindows.org/) |
| Python | Optional developer regression and repository checks | [Python license](https://docs.python.org/3/license.html) |
| actions/checkout | CI checkout | [MIT license](https://github.com/actions/checkout/blob/main/LICENSE) |
| actions/upload-artifact | CI artifact upload | [MIT license](https://github.com/actions/upload-artifact/blob/main/LICENSE) |

The project MIT license covers Patch to Repo's own source, documentation, and included artwork. It does not relicense these external projects. AutoIt compiles the application using its own runtime and standard-library implementation. Consult the upstream terms when changing toolchain distribution or bundling other software. Git is required separately and is not bundled in application archives.
