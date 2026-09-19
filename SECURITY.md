# Security Policy

## Supported versions

Security fixes are accepted for the latest released version of Privacy AI Workstation on the `main` branch.

## What this tool does

This project installs and configures third-party software (package managers, browsers, VPN/email clients, Docker, Ollama, LibreChat, and related tooling). It does **not** handle Mullvad or Proton account credentials.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Prefer one of these private channels:

1. **GitHub Security Advisories** (preferred once the repository is published): use *Report a vulnerability* on the repository Security tab.
2. If advisories are unavailable, contact the maintainer privately through the contact method listed on the GitHub profile or organization that owns the repository.

Include:

- A clear description of the issue
- Affected version / commit when known
- Steps to reproduce
- Impact assessment (what an attacker could gain)
- Any suggested fix, if you have one

You should receive an acknowledgment within a few days. Please give a reasonable window for a fix before any public disclosure.

## Scope notes

In scope examples:

- Command injection or unsafe subprocess usage in this repository’s scripts
- Path traversal or overwrite of unrelated user files by this tool
- Integrity failures (for example, accepting a download without verifying a published checksum when this project claims to verify it)
- Leakage of secrets that this tool itself creates or stores

Out of scope examples:

- Vulnerabilities in upstream projects (Ollama, LibreChat, Brave, Mullvad, Proton Mail, Docker, winget packages, distro packages) — report those upstream
- Issues that require an already-compromised local admin account
- Social engineering or physical access attacks
