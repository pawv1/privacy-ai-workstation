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

### Honest limits (LibreChat / Docker)

Linux is a solid **package installer** for privacy apps + Ollama. It is **not** yet a fully hands-off “one command healthy LibreChat” path on every box.

| Topic | Behavior |
|--------|----------|
| **Docker Engine** | Detect + guide only. Automatic install is intentionally skipped (distro-specific). Install Docker yourself, then rerun. |
| **Ollama daemon** | After install, PAW tries `systemctl` (user/system) then falls back to background `ollama serve` with `OLLAMA_HOST=0.0.0.0:11434`. On odd environments without systemd this still helps, but you may need to keep that process alive. |
| **LibreChat `.env`** | On Linux, PAW upserts Compose-friendly values: `MONGO_URI=mongodb://mongodb:27017/LibreChat`, `MEILI_HOST=http://meilisearch:7700`, `HOST=0.0.0.0`, plus host `UID`/`GID`. |
| **Compose override** | Adds `host.docker.internal:host-gateway` and mounts `librechat.yaml` when no override exists yet. Existing custom overrides are not rewritten. |
| **Bind mounts** | Creates `data-node`, `images`, `uploads`, `logs`, `meili_data*` and best-effort `chown` to the current user (sudo if needed). |
| **`start` health** | After `docker compose up -d`, waits for `http://127.0.0.1:3080`. Failure prints diagnostics guidance. |

### Environments that still break LibreChat

These are **outside** what PAW can fully paper over:

- Nested Docker / Docker-in-Docker forcing the **vfs** storage driver (Meili/Mongo often time out)
- Rootless Docker with unusual UID mapping
- Locked-down hosts where `chown`/`sudo` cannot fix volume ownership
- Very slow disks where 180s health wait is not enough

On a normal desktop with systemd, a real disk, and Docker Engine installed from upstream docs, the Linux start path is much more reliable after the v1.0.1 fixes — but **“Linux just works” for LibreChat is still an open reliability goal**, not a hard guarantee.

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
