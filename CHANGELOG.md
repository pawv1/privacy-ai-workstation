# Changelog

## [Unreleased]

## 1.0.2

LibreChat polish after the overlayfs/WSL acceptance pass:

- Merge `host.docker.internal:host-gateway` into **existing** `docker-compose.override.yml` (backup `.bak` once); still create a full override when missing
- Fill blank LibreChat secrets when empty: `ADMIN_PANEL_SESSION_SECRET`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `CREDS_KEY`, `CREDS_IV`, `MEILI_MASTER_KEY` (never overwrite set values)
- Add `--yes` / `-y` to `repair` for non-interactive use
- Document Linux LibreChat support matrix: normal overlay2/overlayfs desktop supported; nested Docker / vfs unsupported

## 1.0.1

Linux LibreChat / Ollama reliability (partial pass → closer to hands-off on normal desktops):

- Start Ollama when the API is down: try `systemctl`, then background `ollama serve` (Linux defaults `OLLAMA_HOST=0.0.0.0:11434`)
- Patch LibreChat `.env` on Linux for Compose hostnames (`mongodb`, `meilisearch`), `HOST`, and host `UID`/`GID`
- Compose override includes `host.docker.internal:host-gateway` when creating a new override
- Create LibreChat data dirs and best-effort `chown` before `docker compose up`
- `start` waits for `http://127.0.0.1:3080` and logs recovery hints on timeout
- Document honest Linux LibreChat limits (manual Docker Engine; nested Docker/vfs still fragile)

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
