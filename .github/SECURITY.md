# Security Policy

## Supported versions

Security fixes are generally targeted at the latest released version of NovaHost and the current development branch.

Because NovaHost is a local file viewer/server, security reports involving path traversal, unintended file access, code execution, unsafe archive handling, or browser-side injection are especially important.

## Reporting a vulnerability

Please do **not** disclose an unpatched security vulnerability in a public GitHub issue.

Use GitHub's private security advisory/reporting mechanism for this repository when available. If private reporting is not enabled, contact the project maintainer privately before making the issue public.

Include:

- NovaHost version or commit
- Operating system
- Python version
- A clear description of the vulnerability
- Reproduction steps or a minimal proof of concept
- Security impact
- Any suggested mitigation, if known

Please avoid including real secrets, private files, credentials, or personal data in a report.

## Security principles

NovaHost is designed around several security boundaries:

- User-selected roots restrict filesystem access.
- Requested paths are validated before serving.
- Symlinks must not escape the configured root.
- Archives are inspected without blindly extracting them.
- Notebook content is read-only and is not executed.
- SQLite handling is read-only.
- NovaHost does not execute arbitrary uploaded files as part of viewing them.
- Directly served HTML is allowed to behave as browser HTML, so users should only open trusted HTML when active content is a concern.

These are design goals, not a guarantee that vulnerabilities cannot exist. Please report anything that violates the intended security boundary.
