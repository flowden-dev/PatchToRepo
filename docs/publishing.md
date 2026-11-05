# Publishing and releases

## Put the repository on GitHub

Suggested repository name: **PatchToRepo**.

Suggested description:

> Windows context-menu tool for applying Git patches to local repositories, with recent folders and preflight checks. Written in AutoIt.

Suggested topics: `autoit`, `windows`, `git`, `patch`, `context-menu`, `developer-tools`.

1. Extract the repository archive. Use the contents of the `PatchToRepo` folder as the repository root, including `.github`, `.gitignore`, and `.gitattributes`.
2. Review the included MIT license and contributor attribution before publishing. It grants broad reuse of the code and artwork; change it before publication if a different distribution policy is intended.
3. Create an empty GitHub repository without generating another README, license, or `.gitignore`.
4. Upload these files through Git or the GitHub interface. With Git, initialize this folder, add its contents, commit, and connect the remote URL GitHub gives you. Do not upload the ZIP as the sole repository file.
5. Enable GitHub Actions if prompted and inspect both jobs in the first CI run. A failed Windows job must be investigated before publishing an executable.
6. Enable Issues and private vulnerability reporting. Set the description and topics above. Once CI is green, consider protecting the default branch and requiring its checks on pull requests.

The archive contains no `.git` directory, invented remote URL, built binary, credentials, local toolchains, personal repository history, or automatically published release. GitHub Actions does not require repository secrets for the included jobs.

## Release a binary

The workflow creates downloadable build artifacts; it does not publish a GitHub release automatically. This allows a Windows 10 acceptance check before distributing a binary.

1. Resolve changes under Unreleased into the intended application version. Update `VERSION`, native compiler FileVersion/ProductVersion, wrapper Fileversion, and the changelog together when the application version changes. The initial imported application version is 1.0.4.
2. Run repository checks, Git tests, a clean native build, and source/compiled verification on the exact release commit. Confirm CI passed for that commit too.
3. Complete the [manual Windows acceptance](testing.md#manual-windows-acceptance) and record the OS, tool versions, and result.
4. Package that build with `scripts/Package.ps1`, or download the equivalent ZIP and `.sha256` from that successful CI run. Do not mix a binary from one commit with source or checksums from another.
5. If signing is used, sign the tested EXE before packaging and regenerate the ZIP/checksum. The provided pipeline does not sign binaries or contain a signing certificate. Document the publisher and signing status accurately.
6. Create a Git tag matching the version, such as `v1.0.4`, at the exact tested commit. Create a draft GitHub release with that tag.
7. Attach `PatchToRepo-VERSION-win-x64.zip` and its `.sha256`, include the changelog and validation record, and publish the reviewed draft.

For an initial release, a prerelease label is appropriate until the target-machine acceptance checks have passed. Never label a failing or incomplete test run as verified.

## Dependency updates

Dependabot proposes workflow action updates. Review the upstream release and full commit pin; do not enable automatic merging solely because an update is generated. AutoIt toolchain updates are manual: fetch the official versioned archive, independently compute SHA-256, update [the pin](../tools/autoit-toolchain.json), and rerun the Windows build and native tests. A changing `latest` download is not used in CI.

## Packaging contract

The runtime ZIP contains the EXE, runtime README, user guide, MIT license, and third-party notices. It does not contain Git, AutoIt development binaries, test logs, source-only instructions, or private settings. The icon is embedded in the EXE. The repository itself is the complete source distribution.
