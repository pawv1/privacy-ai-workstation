# Privacy AI Workstation

**Version:** 1.0.1

Cross-platform installer and auditor for a **privacy-focused local AI workstation**.

It scans your machine, installs what is missing, skips what is already healthy, and optionally upgrades selected components with `--update`.

**v1.0.x** ships a lean **core** stack (local AI + privacy apps + tooling). It is not a full OS hardener. On Linux, privacy apps + Ollama install cleanly; LibreChat still needs Docker Engine installed manually, and nested/vfs Docker setups can fail even after PAW’s start-path fixes — see [docs/platforms.md](docs/platforms.md) and [ROADMAP.md](ROADMAP.md).

## What you get

| Layer | Components |
|--------|------------|
| Local AI | Ollama + hardware-aware model fit advice |
| Chat UI | LibreChat (Docker), wired to Ollama |
| Privacy browsers | DuckDuckGo + Brave (at least one) |
| VPN | Mullvad VPN app |
| Email | Proton Mail desktop app |
| Tooling | Git, Node.js, Docker, optional VSCodium |

Account login for Mullvad and Proton stays manual. The script installs the apps; it does not handle credentials.

## Supported platforms

| Platform | Status |
|----------|--------|
| Windows 10 / 11 | Supported |
| Linux x86_64 / ARM64 | Supported |
| macOS | Not supported yet |

### What you need *before* running the Python CLI

The main tool is a Python script, so **something** has to provide Python first:

- **Network access** for downloads
- **Windows:** [winget](https://learn.microsoft.com/windows/package-manager/winget/) available (used by bootstrap + app installs)
- **Linux:** a package manager such as `apt`/`dnf`, plus `sudo` for system packages

If Python is missing, use the **bootstrap** helpers below (or install Python manually from [python.org/downloads](https://www.python.org/downloads/)).

### What the script installs for you (if missing)

| Component | Windows | Linux |
|-----------|---------|-------|
| Git, Node.js, VSCodium | Yes | Best-effort |
| Ollama | Yes | Yes |
| Docker / Compose | Yes (Docker Desktop via winget) | Detects; **manual** Engine install |
| LibreChat | Yes — clones, configures, can `--start` | Yes — clones + Linux `.env`/UID/`extra_hosts`/data-dir prep; `--start` waits for `:3080` |
| Brave, DuckDuckGo, Mullvad VPN, Proton Mail | Yes | Brave / Mullvad / Proton yes; DuckDuckGo **no official Linux app** |

So: **LibreChat is pulled by the script.** Docker is installed automatically on Windows when possible; on Linux you often install Docker yourself first, then the script sets up LibreChat on top of it.

### Honest limits (“any machine?”)

It is **not** universal. It will not run on phones, locked-down machines without package install rights, or macOS today. On Linux there is **no official DuckDuckGo Desktop Browser**, so Brave covers privacy browsing there. Some Linux distros may need manual Docker install.

## Quick start

### Option A — No Python yet (recommended for new machines)

**Windows (PowerShell):**

```powershell
.\scripts\bootstrap.ps1
# or just audit first:
.\scripts\bootstrap.ps1 audit
```

This installs **Python 3.12** via winget when needed (`Python.Python.3.12`), then runs the workstation installer.

If winget is unavailable, install Python manually from  
[https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)  
(enable **Add python.exe to PATH**), open a **new** terminal, then re-run bootstrap.

**Linux:**

```bash
chmod +x scripts/bootstrap.sh scripts/install.sh
./scripts/bootstrap.sh
./scripts/bootstrap.sh audit
```

This installs `python3` through `apt`/`dnf`/etc. when needed, then continues.

Manual fallback: [https://www.python.org/downloads/](https://www.python.org/downloads/)

### Option B — Python 3.10+ already installed

```bash
# Audit only (no changes)
python privacy-ai-workstation.py audit

# Install missing pieces
python privacy-ai-workstation.py install

# Install and start LibreChat
python privacy-ai-workstation.py install --start

# Upgrade already-installed components
python privacy-ai-workstation.py install --update
```

Helpers (assume Python is already present):

```powershell
# Windows
.\scripts\install.ps1
.\scripts\install.ps1 audit
```

```bash
# Linux
./scripts/install.sh
./scripts/install.sh audit
```

## Commands

| Command | Purpose |
|---------|---------|
| `--version` / `-V` | Print app version |
| `audit` | Hardware + software scan |
| `status` | Current workstation status |
| `report` | Write JSON report under `~/.llm-workstation/` |
| `models` | List installed Ollama models |
| `install` | Install missing stack pieces |
| `repair` | Fix missing/broken pieces |
| `start` / `stop` | Start or stop LibreChat |

Useful `install` flags: `--dry-run`, `--yes`, `--update`, `--no-privacy`, `--no-librechat`, `--model`, `--pull-model`, `--start`.

## Behavior

1. **Scan** each component  
2. **Install** if missing  
3. **Skip** if healthy  
4. **Update** only when `--update` is passed  

With `--update`, the script currently upgrades:

- Privacy apps on Windows (Brave, DuckDuckGo, Mullvad VPN, Proton Mail via winget)
- LibreChat git checkout + Docker images (when present)

Git, Node, Ollama, Docker, and VSCodium remain **install-if-missing** (they are not force-upgraded yet).

LibreChat is cloned to `~/LibreChat` on new machines. If an existing checkout is found (or remembered), it is reused instead of cloning again.

Runtime reports and the remembered LibreChat path live under `~/.llm-workstation/` (legacy directory name kept for compatibility).

## Project layout

```text
privacy-ai-workstation/
├── privacy-ai-workstation.py   # main CLI (stdlib only)
├── scripts/
│   ├── bootstrap.ps1           # Windows: install Python if needed, then run
│   ├── bootstrap.sh            # Linux: install Python if needed, then run
│   ├── install.ps1             # Windows helper (Python already present)
│   └── install.sh              # Linux helper (Python already present)
├── docs/
│   └── platforms.md            # platform notes
├── .github/workflows/ci.yml    # smoke CI
├── CHANGELOG.md
├── ROADMAP.md                  # planned milestones after v1.0.0
├── SECURITY.md
├── LICENSE
├── README.md
├── .gitignore
└── .gitattributes
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned milestones after v1.0.0 (guided hardening, privacy profile with KeePassXC, optional Open WebUI, creator tools).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities privately.

## License

MIT — see [LICENSE](LICENSE).
