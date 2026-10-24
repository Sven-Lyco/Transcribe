# Security Policy

## Supported versions

Only the latest release gets security fixes. Please check that the problem still occurs with it before reporting.

## Reporting a vulnerability

Please do not open a public issue. Report the problem privately through GitHub instead: **[Report a vulnerability](https://github.com/Sven-Lyco/Transcribe/security/advisories/new)**.

Include the version, your operating system, whether you use the Mac app or the script, and the steps to reproduce the problem.

## Scope

Transcribe runs a web server on `127.0.0.1` that only your own browser or the Mac app's window should use. Reports are especially welcome about:

- other websites reading or changing data through this server,
- reading or deleting files outside the transcription folder,
- the Mac app or its release workflow.

Known limitations, not vulnerabilities:

- Other user accounts on the same computer can reach the local server.
- The Mac app is only signed ad hoc and not notarized by Apple.
