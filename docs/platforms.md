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

- **Brave:** official apt/dnf repos, with vendor `install.sh` as fallback
- **Mullvad VPN:** official Mullvad apt/dnf repository (`mullvad-vpn`)
- **Proton Mail:** official DEB/RPM from Proton (checksum-verified), snap fallback
- **DuckDuckGo Desktop:** no official Linux build — skipped; Brave is the privacy browser on Linux
- **Docker:** detection + guidance; automatic install is distro-specific and may require manual steps
- **Ollama + LibreChat:** LibreChat’s compose config uses `host.docker.internal` to reach Ollama on the host. Ollama often listens on `127.0.0.1` only. If LibreChat cannot list local models on Linux, set `OLLAMA_HOST=0.0.0.0` for the Ollama service (systemd drop-in or environment), restart Ollama, and confirm `curl http://127.0.0.1:11434/api/tags` still works locally.

## macOS

Not supported in this version.

## Environment overrides

| Variable | Purpose |
|----------|---------|
| `PRIVACY_AI_LIBRECHAT_DIR` | Force LibreChat checkout path |
| `LLM_WORKSTATION_LIBRECHAT_DIR` | Legacy alias for the same path |

Remembered path file: `~/.llm-workstation/librechat-path.txt`
