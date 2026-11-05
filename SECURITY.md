# Security policy

Security fixes are intended for the latest published version. Older snapshots are not maintained as separate support branches. The initial repository snapshot has no implied response-time commitment or completed Windows certification.

## Report a vulnerability

Use **Security > Advisories > Report a vulnerability** on the GitHub repository when private vulnerability reporting is enabled. Include the affected version, a minimal reproduction with disposable data, the impact, and any known workaround.

If that option is unavailable, open a public issue asking the maintainer to enable a private reporting channel. Do not post exploit details, sensitive patches, credentials, or private repository data in that issue.

## Trust boundaries

- A patch can change executable source or configuration in the selected repository. Review the patch and resulting diff before building or running affected code.
- Git is an external executable. Install it from a source you trust; **Locate Git...** runs the selected executable to check its version.
- Integration and history are per user. The application does not require elevation or request network credentials.
- Git's normal path and repository ownership protections are preserved. The helper does not use unsafe-path flags or override `safe.directory`.
- Recent repository paths are stored unencrypted in the user's registry. Operation details include local paths and Git output; sanitize them before sharing.
- Native tests use isolated keys and temporary repositories. They do not validate arbitrary untrusted AutoIt modifications.

No telemetry, updater, or network service is implemented. Checksum verification detects changed downloads; it is not a substitute for trusting the release publisher or for code signing.
