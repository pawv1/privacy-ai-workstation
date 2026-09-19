# Changelog

## [Unreleased]

## 1.0.0

First public release.

Includes the privacy AI workstation stack previously developed as internal 2.2.0:

- Rebranded as Privacy AI Workstation
- Privacy stack: Brave, DuckDuckGo, Mullvad VPN, Proton Mail
- LibreChat discovery + clone-if-missing + optional `--update`
- Scan → install-if-missing → skip-if-healthy behavior
- Windows/Linux bootstrap scripts for Python 3.10+
- Accurate install/repair exit codes
- Linux package installs elevate with `sudo`
- Winget-only Windows package IDs (no choco/scoop ID mismatch)
- Wait for Ollama API before model pulls
- VSCodium detection via PATH, winget, and install paths
- Treat winget “already installed / no upgrade” exits as success
- Prefer `py -3` / real Python; skip Microsoft Store `WindowsApps` alias
- CLI `--version` / `-V`
- `SECURITY.md` with private reporting guidance
- GitHub Actions smoke CI (syntax, `--help`, `--version` on Windows and Linux)
- Public `ROADMAP.md` for planned milestones after v1.0.0
