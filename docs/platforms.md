# Platform notes

## Bootstrap (install Python first)

| OS | Script | What it does |
|----|--------|--------------|
| Windows | `scripts/bootstrap.ps1` | Installs `Python.Python.3.12` via winget if needed, then runs the CLI |
| Linux | `scripts/bootstrap.sh` | Installs `python3` via apt/dnf/pacman/etc. if needed, then runs the CLI |

Manual downloads:

- Windows: https://www.python.org/downloads/windows/
- All platforms: https://www.python.org/downloads/

## Windows 10 / 11

Preferred package manager: **winget**.

Installed when missing (unless skipped by flags):

- DuckDuckGo Desktop (`DuckDuckGo.DesktopBrowser`)
- Brave (`Brave.Brave`)
- Mullvad VPN (`MullvadVPN.MullvadVPN`)
- Proton Mail (`Proton.ProtonMail`)
- Ollama, Git, Node.js, Docker Desktop, VSCodium as needed

LibreChat is cloned with Git and started with Docker Compose.

## Linux (x86_64 / ARM64)

### What works well today

- **Brave:** official apt/dnf repos, with vendor `install.sh` as fallback
- **Mullvad VPN:** official Mullvad apt/dnf repository (`mullvad-vpn`)
- **Proton Mail:** official DEB/RPM from Proton (checksum-verified), snap fallback
- **DuckDuckGo Desktop:** no official Linux build — skipped; Brave is the privacy browser on Linux
- **Ollama package install:** official `install.sh` when `curl` is available

### LibreChat support matrix (Linux)

| Environment | LibreChat E2E (`:3080`) | Notes |
|-------------|-------------------------|--------|
| Normal desktop / WSL2 + Docker Engine with **overlay2** / **overlayfs** | **Supported** | Verified with PAW v1.0.1+ (`repair` / `start` → HTTP 200) |
| Nested Docker / Docker-in-Docker with **vfs** | **Unsupported** | DNS may work while TCP between Compose peers times out — not treated as a PAW regression |
| No Docker Engine installed | Blocked | PAW detects/guides only; install Engine yourself, then rerun |

### What PAW configures for LibreChat

| Topic | Behavior |
|--------|----------|
| **Docker Engine** | Detect + guide only. Automatic install is intentionally skipped (distro-specific). |
| **Ollama daemon** | Tries `systemctl`, then background `ollama serve` with `OLLAMA_HOST=0.0.0.0:11434` when needed. |
| **LibreChat `.env`** | Linux: Compose hostnames + `UID`/`GID`. All platforms: fill **blank** secrets (`ADMIN_PANEL_SESSION_SECRET`, JWT/creds/Meili) without overwriting set values. |
| **Compose override** | Creates override with `host.docker.internal:host-gateway` + `librechat.yaml` mount when missing; **merges** `host-gateway` into existing overrides (writes `.bak` once). |
| **Bind mounts** | Creates `data-node`, `images`, `uploads`, `logs`, `meili_data*` and best-effort `chown`. |
| **`start` health** | After `docker compose up -d`, waits for `http://127.0.0.1:3080` and prints diagnostics on failure. |

### Manual recovery (if `:3080` never answers)

From the LibreChat checkout (usually `~/LibreChat`):

```bash
# Confirm Docker + Ollama
docker info
curl -s http://127.0.0.1:11434/api/tags

# Ownership (match your user)
sudo chown -R "$(id -u):$(id -g)" data-node images uploads logs meili_data*

# Restart stack
docker compose down
docker compose up -d
docker compose ps
docker compose logs --tail=100 mongodb meilisearch api
```

## macOS

Not supported in this version.

## Environment overrides

| Variable | Purpose |
|----------|---------|
| `PRIVACY_AI_LIBRECHAT_DIR` | Force LibreChat checkout path |
| `LLM_WORKSTATION_LIBRECHAT_DIR` | Legacy alias for the same path |
| `OLLAMA_HOST` | If set before PAW starts `ollama serve`, honored via environment (Linux default becomes `0.0.0.0:11434` when PAW starts serve itself) |

Remembered path file: `~/.llm-workstation/librechat-path.txt`
