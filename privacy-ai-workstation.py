#!/usr/bin/env python3
"""
Privacy AI Workstation
======================

Cross-platform privacy-focused local AI workstation installer/auditor.

Targets:
    Windows 10/11
    Linux x86_64 / ARM64

Manages:
    - Hardware detection
    - CPU/RAM/storage analysis
    - NVIDIA/AMD/Intel GPU detection
    - Ollama detection/installation
    - Dynamic Ollama model discovery
    - Conservative model compatibility estimation
    - Docker / Docker Compose detection
    - LibreChat installation/configuration
    - Privacy browsers (DuckDuckGo + Brave; at least one required)
    - Mullvad VPN
    - Proton Mail desktop app
    - Node.js / npm detection
    - Git detection
    - VSCodium detection
    - JSON hardware/software reports
    - Status / audit / repair / install modes
    - Scan → install-if-missing → skip-if-healthy
    - Optional --update upgrades already-installed components

Examples:

    python privacy-ai-workstation.py --version
    python privacy-ai-workstation.py audit
    python privacy-ai-workstation.py status
    python privacy-ai-workstation.py install
    python privacy-ai-workstation.py install --update
    python privacy-ai-workstation.py install --model qwen3:8b
    python privacy-ai-workstation.py repair
    python privacy-ai-workstation.py models
    python privacy-ai-workstation.py start
    python privacy-ai-workstation.py stop
    python privacy-ai-workstation.py report

Design principles:

    - Idempotent
    - Conservative model recommendations
    - No model download without explicit request
    - Never overwrite existing LibreChat configuration silently
    - Uses subprocess without shell=True wherever possible
    - Produces machine-readable JSON reports
    - Fails gracefully when optional hardware/software isn't present
    - Does not automate VPN/email account login or credentials
    - Default install skips healthy components; --update opts into upgrades
"""

from __future__ import annotations

import argparse
import datetime as datetime_module
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# CONSTANTS
# ============================================================================

APP_NAME = "Privacy AI Workstation"
APP_VERSION = "1.0.1"

BASE_DIR = Path.home() / ".llm-workstation"
LOG_FILE = BASE_DIR / "llm-workstation.log"
REPORT_FILE = BASE_DIR / "hardware-report.json"
LIBRECHAT_PATH_FILE = BASE_DIR / "librechat-path.txt"

# Official Windows winget package IDs
WINGET_BRAVE = "Brave.Brave"
WINGET_DUCKDUCKGO = "DuckDuckGo.DesktopBrowser"
WINGET_MULLVAD = "MullvadVPN.MullvadVPN"
WINGET_PROTON_MAIL = "Proton.ProtonMail"
WINGET_VSCODIUM = "VSCodium.VSCodium"

# winget often returns these when a package is already installed / up to date
WINGET_SOFT_SUCCESS_CODES = {
    0,
    -1978335189,  # UPDATE_NOT_APPLICABLE / no applicable upgrade
    -1978335135,  # another common "already installed" family code
}

PROTON_MAIL_VERSION_URL = (
    "https://proton.me/download/mail/linux/version.json"
)
BRAVE_LINUX_INSTALL_SH = "https://dl.brave.com/install.sh"
MULLVAD_KEYRING_URL = (
    "https://repository.mullvad.net/deb/mullvad-keyring.asc"
)
MULLVAD_APT_REPO = (
    "deb [signed-by=/usr/share/keyrings/mullvad-keyring.asc "
    "arch={arch}] https://repository.mullvad.net/deb/stable stable main"
)
MULLVAD_FEDORA_REPO = (
    "https://repository.mullvad.net/rpm/stable/mullvad.repo"
)
BRAVE_KEYRING_URL = (
    "https://brave-browser-apt-release.s3.brave.com/"
    "brave-browser-archive-keyring.gpg"
)
BRAVE_APT_SOURCES_URL = (
    "https://brave-browser-apt-release.s3.brave.com/brave-browser.sources"
)
BRAVE_FEDORA_REPO = (
    "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo"
)

OLLAMA_URL = "http://127.0.0.1:11434"

LIBRECHAT_REPO = "https://github.com/danny-avila/LibreChat.git"
DEFAULT_LIBRECHAT_DIR = Path.home() / "LibreChat"

LIBRECHAT_URL = "http://127.0.0.1:3080"

MIN_PYTHON = (3, 10)

# Memory reserve:
# Don't assume 100% of RAM/VRAM belongs to the model.
SYSTEM_RAM_RESERVE = 0.25
GPU_VRAM_RESERVE_GB = 1.0

# Minimum disk space we want left untouched.
MIN_FREE_DISK_GB = 15.0

# Model-name heuristics. Exact model metadata is obtained from Ollama
# when possible, while these values are fallback estimates.
MODEL_HEURISTICS = {
    "1b": 1.5,
    "2b": 2.5,
    "3b": 3.5,
    "4b": 5.0,
    "7b": 8.0,
    "8b": 9.0,
    "9b": 10.0,
    "11b": 12.0,
    "12b": 13.0,
    "13b": 15.0,
    "14b": 17.0,
    "20b": 24.0,
    "22b": 26.0,
    "27b": 32.0,
    "30b": 36.0,
    "32b": 38.0,
    "34b": 40.0,
    "40b": 48.0,
    "70b": 80.0,
    "72b": 82.0,
    "120b": 140.0,
    "405b": 450.0,
}

# ============================================================================
# LOGGING
# ============================================================================


def setup_logging() -> logging.Logger:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8",
    )

    console_handler = logging.StreamHandler()

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


log = setup_logging()


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class GPU:
    index: int
    vendor: str
    name: str
    vram_gb: Optional[float] = None
    driver: Optional[str] = None
    backend: Optional[str] = None
    compute_capability: Optional[str] = None


@dataclass
class Hardware:
    hostname: str
    os: str
    os_version: str
    kernel: str
    architecture: str

    cpu: str
    cpu_threads: int

    ram_total_gb: float
    ram_available_gb: float

    disk_total_gb: float
    disk_free_gb: float

    gpus: list[GPU] = field(default_factory=list)

    virtualization: bool = False

    is_admin: bool = False


@dataclass
class Software:
    python: Optional[str] = None
    git: Optional[str] = None
    node: Optional[str] = None
    npm: Optional[str] = None
    docker: Optional[str] = None
    docker_compose: Optional[str] = None
    ollama: Optional[str] = None
    vscodium: Optional[str] = None
    brave: Optional[str] = None
    duckduckgo: Optional[str] = None
    mullvad_vpn: Optional[str] = None
    proton_mail: Optional[str] = None
    librechat: Optional[str] = None


# ============================================================================
# GENERAL UTILITIES
# ============================================================================


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def resolve_executable(command: str) -> Optional[str]:
    """
    Resolve a command to a concrete executable path.

    On Windows this is required because CreateProcess cannot launch
    bare .cmd/.bat names without going through cmd.exe.
    """

    return shutil.which(command)


def prepare_command(command: list[str]) -> list[str]:
    if not command:
        return command

    if os.name != "nt":
        return command

    resolved = resolve_executable(command[0])
    if not resolved:
        return command

    lower = resolved.lower()
    if lower.endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", resolved, *command[1:]]

    return [resolved, *command[1:]]


def run_command(
    command: list[str],
    timeout: int = 60,
    capture: bool = True,
    cwd: Optional[Path | str] = None,
) -> subprocess.CompletedProcess:
    """
    Safe subprocess wrapper.

    No shell=True. On Windows, .cmd/.bat launchers are invoked via cmd.exe /c.
    """

    prepared = prepare_command(command)
    log.debug("Executing: %s", prepared)

    return subprocess.run(
        prepared,
        timeout=timeout,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        cwd=str(cwd) if cwd else None,
    )


def command_version(command: str) -> Optional[str]:
    if not command_exists(command):
        return None

    try:
        result = run_command(
            [command, "--version"],
            timeout=15,
        )

        output = (
            result.stdout.strip()
            if result.stdout.strip()
            else result.stderr.strip()
        )

        if not output:
            return None

        return output.splitlines()[0]

    except Exception:
        return None


def path_exists_any(paths: list[Path]) -> Optional[Path]:
    for path in paths:
        try:
            if path.exists():
                return path
        except OSError:
            continue
    return None


def windows_program_files() -> list[Path]:
    roots: list[Path] = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    programs = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    if programs.exists():
        roots.append(programs)
    return roots


def winget_package_status(package_id: str) -> Optional[str]:
    """
    Return installed version string from winget list, or None.
    """

    if os.name != "nt" or not command_exists("winget"):
        return None

    try:
        result = run_command(
            [
                "winget",
                "list",
                "--id",
                package_id,
                "--exact",
                "--disable-interactivity",
            ],
            timeout=90,
        )
    except Exception:
        return None

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0 and package_id.lower() not in output.lower():
        return None

    for line in output.splitlines():
        if package_id.lower() not in line.lower():
            continue
        # Typical: Name  Id  Version  [Available]  Source
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3 and parts[1].lower() == package_id.lower():
            return parts[2]
        if package_id.lower() in line.lower():
            tokens = line.split()
            for token in tokens:
                if re.match(r"^\d+(\.\d+)+", token):
                    return token
    return None


def linux_package_installed(package_name: str) -> Optional[str]:
    if command_exists("dpkg-query"):
        try:
            result = run_command(
                [
                    "dpkg-query",
                    "-W",
                    "-f=${Version}",
                    package_name,
                ],
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    if command_exists("rpm"):
        try:
            result = run_command(
                ["rpm", "-q", "--qf", "%{VERSION}", package_name],
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    return None


def snap_package_installed(package_name: str) -> Optional[str]:
    if not command_exists("snap"):
        return None
    try:
        result = run_command(
            ["snap", "list", package_name],
            timeout=30,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if parts and parts[0] == package_name:
                return parts[1] if len(parts) > 1 else "installed"
    except Exception:
        return None
    return None


def flatpak_package_installed(app_id: str) -> Optional[str]:
    if not command_exists("flatpak"):
        return None
    try:
        result = run_command(
            ["flatpak", "info", "--show-version", app_id],
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        return None
    return None


def detect_brave() -> Optional[str]:
    for name in ("brave-browser", "brave"):
        version = command_version(name)
        if version:
            return version

    winget = winget_package_status(WINGET_BRAVE)
    if winget:
        return winget

    if os.name == "nt":
        candidates: list[Path] = []
        for root in windows_program_files():
            candidates.append(
                root
                / "BraveSoftware"
                / "Brave-Browser"
                / "Application"
                / "brave.exe"
            )
        found = path_exists_any(candidates)
        if found:
            return f"installed ({found})"

    linux = linux_package_installed("brave-browser")
    if linux:
        return linux

    flatpak = flatpak_package_installed("com.brave.Browser")
    if flatpak:
        return f"flatpak {flatpak}"

    return None


def detect_duckduckgo() -> Optional[str]:
    for name in ("duckduckgo", "DuckDuckGo"):
        version = command_version(name)
        if version:
            return version

    winget = winget_package_status(WINGET_DUCKDUCKGO)
    if winget:
        return winget

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            local / "Microsoft" / "WindowsApps" / "DuckDuckGo.exe",
            local
            / "Microsoft"
            / "WindowsApps"
            / "DuckDuckGo.DesktopBrowser_ya2fgkz3nks94",
        ]
        # MSIX package folder under WindowsApps / Program Files
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        windows_apps = program_files / "WindowsApps"
        if windows_apps.exists():
            try:
                for child in windows_apps.glob("DuckDuckGo.DesktopBrowser_*"):
                    candidates.append(child)
            except OSError:
                pass
        found = path_exists_any(candidates)
        if found:
            return f"installed ({found})"

    # Official DuckDuckGo desktop browser is Windows/macOS only.
    return None


def detect_mullvad_vpn() -> Optional[str]:
    for name in ("mullvad", "mullvad-vpn"):
        version = command_version(name)
        if version:
            return version

    winget = winget_package_status(WINGET_MULLVAD)
    if winget:
        return winget

    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Mullvad VPN"
            / "resources"
            / "mullvad.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Mullvad VPN"
            / "Mullvad VPN.exe",
        ]
        found = path_exists_any(candidates)
        if found:
            # Prefer CLI version when the found binary supports --version
            version_candidates = []
            if found.name.lower() == "mullvad.exe":
                version_candidates.append(found)
            version_candidates.extend(candidates)
            seen_paths: set[str] = set()
            for candidate in version_candidates:
                key = str(candidate).lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                if not candidate.exists():
                    continue
                try:
                    result = run_command(
                        [str(candidate), "--version"],
                        timeout=15,
                    )
                    output = (
                        result.stdout.strip()
                        or result.stderr.strip()
                    )
                    if output and result.returncode == 0:
                        return output.splitlines()[0]
                except Exception:
                    continue
            return f"installed ({found})"

    for package in ("mullvad-vpn", "mullvad"):
        linux = linux_package_installed(package)
        if linux:
            return linux

    return None


def detect_proton_mail() -> Optional[str]:
    for name in ("proton-mail", "protonmail"):
        version = command_version(name)
        if version:
            return version

    winget = winget_package_status(WINGET_PROTON_MAIL)
    if winget:
        return winget

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            local / "proton_mail" / "Proton Mail.exe",
            local / "Programs" / "Proton" / "Proton Mail" / "Proton Mail.exe",
            local / "Programs" / "Proton Mail" / "Proton Mail.exe",
        ]
        found = path_exists_any(candidates)
        if found:
            return f"installed ({found})"

    linux = linux_package_installed("proton-mail") or linux_package_installed(
        "protonmail-desktop"
    )
    if linux:
        return linux

    snap = snap_package_installed("proton-mail")
    if snap:
        return f"snap {snap}"

    flatpak = flatpak_package_installed("me.proton.Mail")
    if flatpak:
        return f"flatpak {flatpak}"

    return None


def is_microsoft_store_python_alias(path: str) -> bool:
    normalized = path.replace("/", "\\").lower()
    return "\\windowsapps\\" in normalized


def detect_python() -> Optional[str]:
    """
    Prefer a real Python 3.10+ interpreter.

    On Windows, avoid the Microsoft Store `WindowsApps\\python.exe` alias and
    prefer the `py -3` launcher when available.
    """

    if os.name == "nt" and command_exists("py"):
        try:
            result = run_command(
                [
                    "py",
                    "-3",
                    "-c",
                    (
                        "import sys; "
                        "print(sys.version.split()[0]); "
                        "print(sys.executable)"
                    ),
                ],
                timeout=15,
            )
            lines = [
                line.strip()
                for line in (result.stdout or "").splitlines()
                if line.strip()
            ]
            if result.returncode == 0 and len(lines) >= 2:
                version, executable = lines[0], lines[1]
                if not is_microsoft_store_python_alias(executable):
                    parts = version.split(".")
                    if len(parts) >= 2:
                        major, minor = int(parts[0]), int(parts[1])
                        if (major, minor) >= (3, 10):
                            return f"Python {version}"
        except Exception:
            pass

    for name in ("python3", "python"):
        resolved = resolve_executable(name)
        if not resolved:
            continue
        if is_microsoft_store_python_alias(resolved):
            continue
        version = command_version(name)
        if version:
            return version

    return None


def detect_vscodium() -> Optional[str]:
    version = command_version("codium")
    if version:
        return version

    winget = winget_package_status(WINGET_VSCODIUM)
    if winget:
        return winget

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        program_files = Path(
            os.environ.get("PROGRAMFILES", r"C:\Program Files")
        )
        candidates = [
            local / "Programs" / "VSCodium" / "bin" / "codium.cmd",
            local / "Programs" / "VSCodium" / "bin" / "codium.exe",
            local / "Programs" / "VSCodium" / "VSCodium.exe",
            program_files / "VSCodium" / "bin" / "codium.cmd",
            program_files / "VSCodium" / "bin" / "codium.exe",
            program_files / "VSCodium" / "VSCodium.exe",
        ]
        found = path_exists_any(candidates)
        if found:
            # Prefer version from the nearby codium.cmd when possible
            cmd_candidate = found
            if found.suffix.lower() in {".exe"} and found.name.lower() == "vscodium.exe":
                sibling = found.parent / "bin" / "codium.cmd"
                if sibling.exists():
                    cmd_candidate = sibling
            try:
                result = run_command(
                    [str(cmd_candidate), "--version"],
                    timeout=15,
                )
                output = (
                    result.stdout.strip()
                    or result.stderr.strip()
                )
                if output and result.returncode == 0:
                    return output.splitlines()[0]
            except Exception:
                pass
            return f"installed ({found})"

    linux = linux_package_installed("codium")
    if linux:
        return linux

    return None


def bytes_to_gb(value: int) -> float:
    return round(value / (1024 ** 3), 2)


def gb(value: Optional[float]) -> str:
    if value is None:
        return "unknown"

    if value >= 1024:
        return f"{value / 1024:.1f} TB"

    return f"{value:.1f} GB"


def ask_yes_no(
    question: str,
    default: bool = False,
) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"

    try:
        response = input(
            f"{question} {suffix} "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default

    if not response:
        return default

    return response in {
        "y",
        "yes",
    }


def is_admin() -> bool:
    try:
        if os.name == "nt":
            import ctypes

            return bool(
                ctypes.windll.shell32.IsUserAnAdmin()
            )

        return os.geteuid() == 0

    except Exception:
        return False


def normalize_version(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    match = re.search(
        r"(\d+(?:\.\d+)+)",
        value,
    )

    return match.group(1) if match else value


# ============================================================================
# MEMORY DETECTION
# ============================================================================


def get_total_ram() -> int:
    # Windows
    if os.name == "nt":
        try:
            result = run_command(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
                timeout=10,
            )

            if result.returncode == 0:
                return int(result.stdout.strip())

        except Exception:
            pass

    # Linux
    meminfo = Path("/proc/meminfo")

    if meminfo.exists():
        try:
            text = meminfo.read_text(
                encoding="utf-8",
                errors="replace",
            )

            match = re.search(
                r"^MemTotal:\s+(\d+)\s+kB",
                text,
                re.MULTILINE,
            )

            if match:
                return int(match.group(1)) * 1024

        except Exception:
            pass

    return 0


def get_available_ram() -> int:
    # Windows
    if os.name == "nt":
        try:
            result = run_command(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-Counter '\\Memory\\Available MBytes').CounterSamples.CookedValue",
                ],
                timeout=10,
            )

            if result.returncode == 0:
                return int(float(result.stdout.strip()) * 1024 * 1024)

        except Exception:
            pass

    # Linux
    meminfo = Path("/proc/meminfo")

    if meminfo.exists():
        try:
            text = meminfo.read_text(
                encoding="utf-8",
                errors="replace",
            )

            match = re.search(
                r"^MemAvailable:\s+(\d+)\s+kB",
                text,
                re.MULTILINE,
            )

            if match:
                return int(match.group(1)) * 1024

        except Exception:
            pass

    return get_total_ram()


# ============================================================================
# CPU DETECTION
# ============================================================================


def detect_cpu() -> tuple[str, int]:
    threads = os.cpu_count() or 1

    if os.name == "nt":
        try:
            result = run_command(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
                ],
                timeout=10,
            )

            if result.returncode == 0:
                cpu = result.stdout.strip()

                if cpu:
                    return cpu, threads

        except Exception:
            pass

    if Path("/proc/cpuinfo").exists():
        try:
            text = Path("/proc/cpuinfo").read_text(
                encoding="utf-8",
                errors="replace",
            )

            for key in (
                "model name",
                "Hardware",
                "Processor",
            ):
                match = re.search(
                    rf"^{re.escape(key)}\s*:\s*(.+)$",
                    text,
                    re.MULTILINE,
                )

                if match:
                    return match.group(1).strip(), threads

        except Exception:
            pass

    return (
        platform.processor()
        or platform.machine()
        or "Unknown CPU",
        threads,
    )


# ============================================================================
# GPU DETECTION
# ============================================================================


def detect_nvidia_gpus() -> list[GPU]:
    if not command_exists("nvidia-smi"):
        return []

    try:
        result = run_command(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            timeout=20,
        )

        if result.returncode != 0:
            return []

        gpus: list[GPU] = []

        for line in result.stdout.splitlines():
            parts = [
                x.strip()
                for x in line.split(",")
            ]

            if len(parts) < 5:
                continue

            index, name, memory, driver, compute = parts[:5]

            try:
                vram = float(memory) / 1024
            except Exception:
                vram = None

            try:
                gpu_index = int(index)
            except Exception:
                gpu_index = len(gpus)

            gpus.append(
                GPU(
                    index=gpu_index,
                    vendor="NVIDIA",
                    name=name,
                    vram_gb=round(vram, 2)
                    if vram is not None
                    else None,
                    driver=driver,
                    backend="CUDA",
                    compute_capability=compute,
                )
            )

        return gpus

    except Exception as exc:
        log.debug(
            "NVIDIA detection failed: %s",
            exc,
        )

        return []


def detect_windows_gpus() -> list[GPU]:
    if os.name != "nt":
        return []

    try:
        command = """
        Get-CimInstance Win32_VideoController |
        Select-Object Name,AdapterRAM,DriverVersion |
        ConvertTo-Json -Compress
        """

        result = run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            timeout=20,
        )

        if result.returncode != 0:
            return []

        data = json.loads(
            result.stdout
        )

        if isinstance(data, dict):
            data = [data]

        gpus: list[GPU] = []

        for index, item in enumerate(data):
            name = (
                item.get("Name")
                or "Unknown GPU"
            )

            name_lower = name.lower()

            if "nvidia" in name_lower:
                vendor = "NVIDIA"
                backend = "CUDA"

            elif (
                "amd" in name_lower
                or "radeon" in name_lower
            ):
                vendor = "AMD"
                backend = "Vulkan/ROCm"

            elif "intel" in name_lower:
                vendor = "Intel"
                backend = "Vulkan"

            else:
                vendor = "Unknown"
                backend = "Unknown"

            vram = None

            try:
                if item.get("AdapterRAM"):
                    vram = round(
                        int(item["AdapterRAM"])
                        / (1024 ** 3),
                        2,
                    )
            except Exception:
                pass

            gpus.append(
                GPU(
                    index=index,
                    vendor=vendor,
                    name=name,
                    vram_gb=vram,
                    driver=item.get("DriverVersion"),
                    backend=backend,
                )
            )

        return gpus

    except Exception as exc:
        log.debug(
            "Windows GPU detection failed: %s",
            exc,
        )

        return []


def detect_linux_display_gpus() -> list[GPU]:
    if os.name == "nt":
        return []

    if not command_exists("lspci"):
        return []

    try:
        result = run_command(
            ["lspci"],
            timeout=15,
        )

        gpus: list[GPU] = []

        for line in result.stdout.splitlines():
            lower = line.lower()

            if not any(
                item in lower
                for item in (
                    "vga compatible controller",
                    "3d controller",
                    "display controller",
                )
            ):
                continue

            if "nvidia" in lower:
                vendor = "NVIDIA"
                backend = "CUDA"

            elif (
                "amd" in lower
                or "advanced micro devices" in lower
                or "radeon" in lower
            ):
                vendor = "AMD"
                backend = "Vulkan/ROCm"

            elif "intel" in lower:
                vendor = "Intel"
                backend = "Vulkan"

            else:
                vendor = "Unknown"
                backend = "Unknown"

            name = line.split(
                ": ",
                1,
            )[-1].strip()

            gpus.append(
                GPU(
                    index=len(gpus),
                    vendor=vendor,
                    name=name,
                    backend=backend,
                )
            )

        return gpus

    except Exception:
        return []


def detect_gpus() -> list[GPU]:
    nvidia = detect_nvidia_gpus()

    if nvidia:
        return nvidia

    if os.name == "nt":
        return detect_windows_gpus()

    return detect_linux_display_gpus()


# ============================================================================
# STORAGE
# ============================================================================


def detect_storage() -> tuple[float, float]:
    try:
        usage = shutil.disk_usage(
            Path.home()
        )

        return (
            bytes_to_gb(usage.total),
            bytes_to_gb(usage.free),
        )

    except Exception:
        return (
            0.0,
            0.0,
        )


# ============================================================================
# VIRTUALIZATION
# ============================================================================


def detect_virtualization() -> bool:
    if os.name == "nt":
        try:
            result = run_command(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).Model",
                ],
                timeout=10,
            )

            value = result.stdout.lower()

            return any(
                marker in value
                for marker in (
                    "virtual",
                    "vmware",
                    "virtualbox",
                    "kvm",
                    "hyper-v",
                )
            )

        except Exception:
            return False

    if command_exists("systemd-detect-virt"):
        try:
            result = run_command(
                ["systemd-detect-virt"],
                timeout=5,
            )

            return (
                result.returncode == 0
                and result.stdout.strip()
                not in {
                    "",
                    "none",
                }
            )

        except Exception:
            pass

    return False


# ============================================================================
# HARDWARE AUDIT
# ============================================================================


def audit_hardware() -> Hardware:
    cpu, threads = detect_cpu()

    total_ram = get_total_ram()
    available_ram = get_available_ram()

    disk_total, disk_free = detect_storage()

    return Hardware(
        hostname=socket.gethostname(),
        os=platform.system(),
        os_version=platform.version(),
        kernel=platform.release(),
        architecture=platform.machine(),

        cpu=cpu,
        cpu_threads=threads,

        ram_total_gb=bytes_to_gb(total_ram),
        ram_available_gb=bytes_to_gb(available_ram),

        disk_total_gb=disk_total,
        disk_free_gb=disk_free,

        gpus=detect_gpus(),

        virtualization=detect_virtualization(),

        is_admin=is_admin(),
    )


# ============================================================================
# SOFTWARE AUDIT
# ============================================================================


def audit_software() -> Software:
    compose_version = None

    if command_exists("docker"):
        try:
            result = run_command(
                [
                    "docker",
                    "compose",
                    "version",
                ],
                timeout=15,
            )

            if result.returncode == 0:
                compose_version = (
                    result.stdout.strip()
                    or result.stderr.strip()
                )

        except Exception:
            pass

    return Software(
        python=detect_python(),

        git=command_version("git"),

        node=command_version("node"),

        npm=command_version("npm"),

        docker=command_version("docker"),

        docker_compose=compose_version,

        ollama=command_version("ollama"),

        vscodium=detect_vscodium(),

        brave=detect_brave(),

        duckduckgo=detect_duckduckgo(),

        mullvad_vpn=detect_mullvad_vpn(),

        proton_mail=detect_proton_mail(),

        librechat=detect_librechat(),
    )


# ============================================================================
# OLLAMA
# ============================================================================


def ollama_api_available() -> bool:
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_URL}/api/tags",
            timeout=5,
        ):
            return True

    except Exception:
        return False


def wait_for_ollama(
    timeout: int = 30,
) -> bool:
    end = time.time() + timeout

    while time.time() < end:
        if ollama_api_available():
            return True

        time.sleep(1)

    return False


def _linux_uid_gid() -> tuple[Optional[str], Optional[str]]:
    if os.name == "nt":
        return None, None
    try:
        return str(os.getuid()), str(os.getgid())
    except AttributeError:
        return None, None


def ensure_ollama_running(
    *,
    timeout: int = 45,
    dry_run: bool = False,
) -> bool:
    """
    Make sure the Ollama HTTP API is reachable.

    On Linux desktops without a working systemd user/service unit, install.sh
    alone is not enough — `ollama serve` must be running. We try systemd first,
    then fall back to a background `ollama serve` with OLLAMA_HOST suitable for
    Docker containers reaching the host.
    """

    if ollama_api_available():
        return True

    if not command_exists("ollama"):
        log.error("Ollama is not installed.")
        return False

    if dry_run:
        log.info("[DRY RUN] Would start Ollama API if it is not running.")
        return True

    log.info("Ollama API is not responding; attempting to start it...")

    started = False

    if os.name != "nt" and command_exists("systemctl"):
        for command in (
            ["systemctl", "--user", "start", "ollama"],
            ["systemctl", "start", "ollama"],
            ["sudo", "systemctl", "start", "ollama"],
        ):
            try:
                result = run_command(command, timeout=30)
                if result.returncode == 0:
                    started = True
                    log.info("Started Ollama via: %s", " ".join(command))
                    break
            except Exception:
                continue

    if not started:
        env = os.environ.copy()
        # Containers (LibreChat) need to reach the host listener.
        if os.name != "nt":
            env.setdefault("OLLAMA_HOST", "0.0.0.0:11434")

        log.info(
            "Starting `ollama serve` in the background%s...",
            " (OLLAMA_HOST=0.0.0.0:11434)" if os.name != "nt" else "",
        )
        try:
            # Detached process; do not capture — serve is long-lived.
            kwargs: dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
                "env": env,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                ) | getattr(subprocess, "DETACHED_PROCESS", 0)
            else:
                kwargs["start_new_session"] = True

            subprocess.Popen(["ollama", "serve"], **kwargs)
            started = True
        except Exception as exc:
            log.error("Could not start `ollama serve`: %s", exc)
            return False

    if wait_for_ollama(timeout=timeout):
        return True

    log.error(
        "Ollama did not become ready at %s within %ss. "
        "Start it manually (`ollama serve` or your service manager), then retry.",
        OLLAMA_URL,
        timeout,
    )
    return False


def ollama_models() -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_URL}/api/tags",
            timeout=10,
        ) as response:

            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        return payload.get(
            "models",
            [],
        )

    except Exception as exc:
        log.debug(
            "Could not query Ollama: %s",
            exc,
        )

        return []


def ollama_model_names() -> list[str]:
    return [
        model.get("name")
        for model in ollama_models()
        if model.get("name")
    ]


def ollama_model_details(
    model: str,
) -> Optional[dict[str, Any]]:
    data = json.dumps(
        {"name": model}
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/show",
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except Exception:
        return None


# ============================================================================
# MODEL MEMORY ESTIMATION
# ============================================================================


def extract_parameter_size(
    model_name: str,
) -> Optional[float]:
    """
    Attempts to extract a parameter count from model names such as:

        qwen3:8b
        llama3.1:70b
        some-model:14B-instruct
    """

    match = re.search(
        r"(?:^|[:\-_])(\d+(?:\.\d+)?)b(?:$|[:\-_])",
        model_name.lower(),
    )

    if not match:
        match = re.search(
            r"(\d+(?:\.\d+)?)b",
            model_name.lower(),
        )

    if not match:
        return None

    try:
        return float(
            match.group(1)
        )

    except Exception:
        return None


def estimate_model_memory(
    model_name: str,
    model_size_bytes: Optional[int] = None,
) -> Optional[float]:

    if model_size_bytes:
        # Ollama's stored size is a useful practical lower-bound estimate.
        return round(
            model_size_bytes / (1024 ** 3),
            2,
        )

    params = extract_parameter_size(
        model_name
    )

    if params is None:
        return None

    # Fallback assumes a quantized model around 5-6 bits/parameter plus
    # runtime overhead. This is deliberately conservative.
    if params <= 4:
        multiplier = 1.25
    elif params <= 14:
        multiplier = 1.15
    elif params <= 34:
        multiplier = 1.10
    else:
        multiplier = 1.15

    return round(
        params * multiplier,
        2,
    )


# ============================================================================
# MODEL COMPATIBILITY
# ============================================================================


def total_gpu_vram(
    hardware: Hardware,
) -> float:
    """
    Combined VRAM.

    We don't automatically assume multiple GPUs behave like one giant
    unified VRAM pool. This is only used as an informational upper bound.
    """

    return round(
        sum(
            gpu.vram_gb or 0
            for gpu in hardware.gpus
        ),
        2,
    )


def largest_gpu_vram(
    hardware: Hardware,
) -> float:
    return max(
        (
            gpu.vram_gb or 0
            for gpu in hardware.gpus
        ),
        default=0.0,
    )


def usable_ram(
    hardware: Hardware,
) -> float:
    return round(
        hardware.ram_total_gb
        * (1.0 - SYSTEM_RAM_RESERVE),
        2,
    )


def estimate_context_overhead(
    model_memory_gb: float,
) -> float:
    """
    Runtime/context safety allowance.

    This is not a claim about an exact model's KV-cache requirements.
    It is a conservative additional budget.
    """

    if model_memory_gb < 8:
        return 1.5

    if model_memory_gb < 20:
        return 3.0

    if model_memory_gb < 40:
        return 6.0

    return 10.0


def classify_model(
    hardware: Hardware,
    model_name: str,
    model_size_bytes: Optional[int] = None,
) -> dict[str, Any]:

    model_memory = estimate_model_memory(
        model_name,
        model_size_bytes,
    )

    if model_memory is None:
        return {
            "model": model_name,
            "status": "UNKNOWN",
            "reason": "Could not estimate model memory.",
        }

    runtime_memory = (
        model_memory
        + estimate_context_overhead(
            model_memory
        )
    )

    ram_budget = usable_ram(
        hardware
    )

    gpu_vram = largest_gpu_vram(
        hardware
    )

    usable_gpu_vram = max(
        0.0,
        gpu_vram - GPU_VRAM_RESERVE_GB,
    )

    disk_ok = (
        hardware.disk_free_gb
        >= runtime_memory + MIN_FREE_DISK_GB
    )

    if (
        usable_gpu_vram >= runtime_memory
        and disk_ok
    ):
        status = "FULL_GPU"

        reason = (
            "Estimated runtime memory fits within "
            "the largest detected GPU's usable VRAM."
        )

    elif (
        ram_budget >= runtime_memory
        and disk_ok
    ):
        status = "CPU_OR_OFFLOAD"

        reason = (
            "Estimated runtime memory fits within "
            "the conservative system RAM budget."
        )

    elif (
        ram_budget + usable_gpu_vram
        >= runtime_memory
        and disk_ok
    ):
        status = "HYBRID"

        reason = (
            "Model may require CPU/GPU offloading."
        )

    elif not disk_ok:
        status = "INSUFFICIENT_DISK"

        reason = (
            "Insufficient free storage while preserving "
            "the configured disk safety margin."
        )

    else:
        status = "NOT_RECOMMENDED"

        reason = (
            "Estimated runtime memory exceeds the "
            "conservative available memory budget."
        )

    return {
        "model": model_name,
        "status": status,
        "estimated_model_gb": model_memory,
        "estimated_runtime_gb": round(
            runtime_memory,
            2,
        ),
        "usable_ram_gb": ram_budget,
        "usable_gpu_vram_gb": round(
            usable_gpu_vram,
            2,
        ),
        "reason": reason,
    }


def analyze_ollama_models(
    hardware: Hardware,
) -> list[dict[str, Any]]:

    models = ollama_models()

    results = []

    for model in models:
        name = model.get("name")

        if not name:
            continue

        results.append(
            classify_model(
                hardware,
                name,
                model.get("size"),
            )
        )

    return results


# ============================================================================
# RECOMMENDED CATALOG
# ============================================================================


FALLBACK_MODELS = [
    "qwen3:4b",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3:30b",
    "qwen3:32b",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "llama3.2:3b",
    "llama3.2:8b",
]


def recommended_catalog(
    hardware: Hardware,
) -> list[dict[str, Any]]:

    output = []

    for model in FALLBACK_MODELS:
        result = classify_model(
            hardware,
            model,
        )

        output.append(result)

    priority = {
        "FULL_GPU": 0,
        "HYBRID": 1,
        "CPU_OR_OFFLOAD": 2,
        "INSUFFICIENT_DISK": 3,
        "NOT_RECOMMENDED": 4,
        "UNKNOWN": 5,
    }

    output.sort(
        key=lambda item: (
            priority.get(
                item["status"],
                99,
            ),
            item.get(
                "estimated_runtime_gb",
                999999,
            ),
        )
    )

    return output


# ============================================================================
# PACKAGE MANAGERS
# ============================================================================


def linux_package_manager() -> Optional[str]:
    for manager in (
        "apt-get",
        "dnf",
        "yum",
        "pacman",
        "zypper",
        "apk",
    ):
        if command_exists(manager):
            return manager

    return None


def windows_package_manager() -> Optional[str]:
    if command_exists("winget"):
        return "winget"

    if command_exists("choco"):
        return "choco"

    if command_exists("scoop"):
        return "scoop"

    return None


def run_as_root(command: list[str], *, dry_run: bool = False) -> bool:
    """
    Run a Linux package command with sudo when not root.
    """

    if os.name == "nt":
        return False

    full = list(command)
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        if not command_exists("sudo"):
            log.warning(
                "Root privileges are required for: %s",
                " ".join(command),
            )
            return False
        full = ["sudo", *command]

    if dry_run:
        log.info("[DRY RUN] %s", " ".join(full))
        return True

    try:
        result = run_command(full, timeout=900, capture=False)
        return result.returncode == 0
    except Exception as exc:
        log.error("Privileged command failed: %s", exc)
        return False


def install_package(
    package: str,
    *,
    dry_run: bool = False,
) -> bool:

    if os.name == "nt":
        manager = windows_package_manager()

        if not manager:
            log.warning(
                "No supported Windows package manager found."
            )
            return False

        # Package IDs in this project are winget IDs (Publisher.Product).
        # Do not pass them to choco/scoop unchanged.
        if manager != "winget":
            log.warning(
                "Windows package '%s' requires winget "
                "(found package manager: %s). "
                "Install winget, then re-run.",
                package,
                manager,
            )
            return False

        command = [
            "winget",
            "install",
            "--id",
            package,
            "--exact",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ]

        if dry_run:
            log.info("[DRY RUN] %s", " ".join(command))
            return True

        try:
            result = run_command(
                command,
                timeout=900,
                capture=True,
            )
            if winget_result_ok(result):
                if result.returncode != 0:
                    log.info(
                        "%s is already installed or current "
                        "(winget exit code %s).",
                        package,
                        result.returncode,
                    )
                return True

            # Fall back: package may already be present despite a noisy exit
            if winget_package_status(package):
                log.info(
                    "%s is already installed according to winget list.",
                    package,
                )
                return True

            output = (
                (result.stdout or "")
                + "\n"
                + (result.stderr or "")
            ).strip()
            if output:
                log.error(
                    "winget install failed for %s:\n%s",
                    package,
                    "\n".join(output.splitlines()[-20:]),
                )
            else:
                log.error(
                    "winget install failed for %s (exit %s).",
                    package,
                    result.returncode,
                )
            return False
        except Exception as exc:
            log.error("Package installation failed: %s", exc)
            return False

    manager = linux_package_manager()

    if not manager:
        log.warning(
            "No supported Linux package manager found."
        )
        return False

    if manager == "apt-get":
        command = [
            "apt-get",
            "install",
            "-y",
            package,
        ]

    elif manager in {
        "dnf",
        "yum",
    }:
        command = [
            manager,
            "install",
            "-y",
            package,
        ]

    elif manager == "pacman":
        command = [
            "pacman",
            "-S",
            "--noconfirm",
            package,
        ]

    elif manager == "zypper":
        command = [
            "zypper",
            "--non-interactive",
            "install",
            package,
        ]

    elif manager == "apk":
        command = [
            "apk",
            "add",
            package,
        ]

    else:
        return False

    # Linux system packages need root.
    return run_as_root(command, dry_run=dry_run)


def winget_result_ok(result: subprocess.CompletedProcess) -> bool:
    """
    Treat common winget 'already installed / no upgrade' exits as success.
    """

    if result.returncode in WINGET_SOFT_SUCCESS_CODES:
        return True

    output = (
        (result.stdout or "")
        + "\n"
        + (result.stderr or "")
    ).lower()

    markers = (
        "already installed",
        "no applicable update",
        "no available upgrade",
        "no newer package versions",
        "no updates available",
        "newer version installed",
        "a higher version was found",
        "nothing to do",
    )
    return any(marker in output for marker in markers)


def upgrade_package(
    package: str,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Best-effort upgrade for an already-installed package.

    Missing updates are treated as success (already current).
    """

    if os.name == "nt":
        if windows_package_manager() != "winget":
            log.info(
                "Upgrade skipped for %s (winget unavailable).",
                package,
            )
            return True

        command = [
            "winget",
            "upgrade",
            "--id",
            package,
            "--exact",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ]
    else:
        manager = linux_package_manager()
        if manager == "apt-get":
            command = ["apt-get", "install", "--only-upgrade", "-y", package]
        elif manager in {"dnf", "yum"}:
            command = [manager, "upgrade", "-y", package]
        elif manager == "pacman":
            command = ["pacman", "-S", "--noconfirm", package]
        else:
            log.info(
                "Upgrade skipped for %s on this Linux package manager.",
                package,
            )
            return True

        if hasattr(os, "geteuid") and os.geteuid() != 0:
            if command_exists("sudo"):
                command = ["sudo", *command]
            else:
                log.warning(
                    "Root required to upgrade %s.",
                    package,
                )
                return False

    if dry_run:
        log.info("[DRY RUN] %s", " ".join(command))
        return True

    try:
        result = run_command(
            command,
            timeout=900,
            capture=True,
        )

        if winget_result_ok(result) if os.name == "nt" else result.returncode == 0:
            if result.returncode == 0:
                log.info("Upgraded or confirmed current: %s", package)
            else:
                log.info("%s is already up to date.", package)
            return True

        if os.name != "nt":
            output = (
                (result.stdout or "")
                + "\n"
                + (result.stderr or "")
            ).lower()
            if any(
                marker in output
                for marker in (
                    "already installed",
                    "nothing to do",
                    "no packages marked for update",
                )
            ):
                log.info("%s is already up to date.", package)
                return True

        log.warning(
            "Upgrade of %s returned code %s.",
            package,
            result.returncode,
        )
        return False

    except Exception as exc:
        log.error("Package upgrade failed: %s", exc)
        return False


# ============================================================================
# BASIC SOFTWARE INSTALLATION
# ============================================================================


def ensure_git(
    dry_run: bool = False,
) -> bool:

    if command_exists("git"):
        return True

    if os.name == "nt":
        return install_package(
            "Git.Git",
            dry_run=dry_run,
        )

    return install_package(
        "git",
        dry_run=dry_run,
    )


def ensure_node(
    dry_run: bool = False,
) -> bool:

    if command_exists("node"):
        return True

    if os.name == "nt":
        return install_package(
            "OpenJS.NodeJS.LTS",
            dry_run=dry_run,
        )

    # Linux package managers vary considerably in Node versions.
    # Install from the distro manager only when available.
    return install_package(
        "nodejs",
        dry_run=dry_run,
    )


def ensure_vscodium(
    dry_run: bool = False,
) -> bool:

    detected = detect_vscodium()
    if detected:
        log.info(
            "VSCodium already installed (%s). Skipping.",
            detected,
        )
        return True

    log.info("VSCodium not found. Installing...")

    if os.name == "nt":
        return install_package(
            WINGET_VSCODIUM,
            dry_run=dry_run,
        )

    # Package name is available on some distributions but not all.
    # Failure is non-fatal.
    return install_package(
        "codium",
        dry_run=dry_run,
    )


# ============================================================================
# PRIVACY STACK INSTALLATION
# ============================================================================


def download_file(url: str, destination: Path) -> bool:
    try:
        log.info("Downloading %s", url)
        urllib.request.urlretrieve(url, destination)
        return destination.exists() and destination.stat().st_size > 0
    except Exception as exc:
        log.error("Download failed: %s", exc)
        return False


def sha512_file(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def ensure_brave(dry_run: bool = False, update: bool = False) -> bool:
    detected = detect_brave()
    if detected:
        if update and os.name == "nt":
            log.info(
                "Brave found (%s). Updating because --update was requested...",
                detected,
            )
            return upgrade_package(WINGET_BRAVE, dry_run=dry_run)
        log.info("Brave already installed (%s). Skipping.", detected)
        return True

    log.info("Brave not found. Installing...")

    if os.name == "nt":
        return install_package(WINGET_BRAVE, dry_run=dry_run)

    manager = linux_package_manager()

    if manager == "apt-get":
        if dry_run:
            log.info(
                "[DRY RUN] Would add Brave apt repository and install brave-browser"
            )
            return True

        ok = True
        ok = run_as_root(
            [
                "curl",
                "-fsSLo",
                "/usr/share/keyrings/brave-browser-archive-keyring.gpg",
                BRAVE_KEYRING_URL,
            ],
            dry_run=dry_run,
        ) and ok
        ok = run_as_root(
            [
                "curl",
                "-fsSLo",
                "/etc/apt/sources.list.d/brave-browser-release.sources",
                BRAVE_APT_SOURCES_URL,
            ],
            dry_run=dry_run,
        ) and ok
        ok = run_as_root(["apt-get", "update"], dry_run=dry_run) and ok
        ok = run_as_root(
            ["apt-get", "install", "-y", "brave-browser"],
            dry_run=dry_run,
        ) and ok
        return bool(detect_brave()) if not dry_run else ok

    if manager in {"dnf", "yum"}:
        if dry_run:
            log.info(
                "[DRY RUN] Would add Brave dnf repository and install brave-browser"
            )
            return True
        ok = run_as_root(
            [
                manager,
                "config-manager",
                "addrepo",
                f"--from-repofile={BRAVE_FEDORA_REPO}",
            ],
            dry_run=dry_run,
        )
        if not ok:
            ok = run_as_root(
                [
                    manager,
                    "config-manager",
                    "--add-repo",
                    BRAVE_FEDORA_REPO,
                ],
                dry_run=dry_run,
            )
        ok = run_as_root(
            [manager, "install", "-y", "brave-browser"],
            dry_run=dry_run,
        ) and ok
        return bool(detect_brave()) if not dry_run else ok

    # Vendor one-liner fallback (logged explicitly).
    if command_exists("curl"):
        log.warning(
            "Using Brave's official install.sh fallback for this distribution."
        )
        if dry_run:
            log.info(
                "[DRY RUN] curl -fsS %s | sh",
                BRAVE_LINUX_INSTALL_SH,
            )
            return True
        try:
            result = run_command(
                ["bash", "-lc", f"curl -fsS {BRAVE_LINUX_INSTALL_SH} | sh"],
                timeout=900,
                capture=False,
            )
            return result.returncode == 0 and bool(detect_brave())
        except Exception as exc:
            log.error("Brave install.sh failed: %s", exc)
            return False

    log.warning("Could not install Brave automatically on this Linux system.")
    return False


def ensure_duckduckgo(dry_run: bool = False, update: bool = False) -> bool:
    detected = detect_duckduckgo()
    if detected:
        if update and os.name == "nt":
            log.info(
                "DuckDuckGo found (%s). Updating because --update was requested...",
                detected,
            )
            return upgrade_package(WINGET_DUCKDUCKGO, dry_run=dry_run)
        log.info(
            "DuckDuckGo already installed (%s). Skipping.",
            detected,
        )
        return True

    log.info("DuckDuckGo not found. Installing...")

    if os.name == "nt":
        return install_package(WINGET_DUCKDUCKGO, dry_run=dry_run)

    log.warning(
        "DuckDuckGo Desktop Browser has no official Linux build. "
        "Skipping DuckDuckGo on Linux; Brave covers privacy browsing."
    )
    return False


def ensure_privacy_browsers(
    dry_run: bool = False,
    update: bool = False,
) -> bool:
    """
    Install DuckDuckGo and Brave. Success if at least one is present afterward.
    """

    duck = ensure_duckduckgo(dry_run=dry_run, update=update)
    brave = ensure_brave(dry_run=dry_run, update=update)

    if dry_run:
        # On Linux, DuckDuckGo is expected to soft-fail; Brave must succeed.
        if os.name == "nt":
            return duck and brave
        return brave

    have_duck = bool(detect_duckduckgo())
    have_brave = bool(detect_brave())

    if have_duck and have_brave:
        log.info("Privacy browsers ready: DuckDuckGo and Brave.")
        return True

    if have_duck or have_brave:
        missing = "Brave" if have_duck else "DuckDuckGo"
        log.warning(
            "Only one privacy browser is available (%s missing). Continuing.",
            missing,
        )
        return True

    log.error("No privacy browser could be installed.")
    return False


def ensure_mullvad_vpn(dry_run: bool = False, update: bool = False) -> bool:
    detected = detect_mullvad_vpn()
    if detected:
        if update and os.name == "nt":
            log.info(
                "Mullvad VPN found (%s). Updating because --update was requested...",
                detected,
            )
            return upgrade_package(WINGET_MULLVAD, dry_run=dry_run)
        log.info(
            "Mullvad VPN already installed (%s). Skipping.",
            detected,
        )
        return True

    log.info("Mullvad VPN not found. Installing...")

    if os.name == "nt":
        return install_package(WINGET_MULLVAD, dry_run=dry_run)

    manager = linux_package_manager()

    if manager == "apt-get":
        if dry_run:
            log.info(
                "[DRY RUN] Would add Mullvad apt repository and install mullvad-vpn"
            )
            return True
        arch_result = run_command(
            ["dpkg", "--print-architecture"],
            timeout=15,
        )
        arch = (arch_result.stdout or "amd64").strip() or "amd64"
        repo_line = MULLVAD_APT_REPO.format(arch=arch)
        ok = run_as_root(
            [
                "curl",
                "-fsSLo",
                "/usr/share/keyrings/mullvad-keyring.asc",
                MULLVAD_KEYRING_URL,
            ],
            dry_run=dry_run,
        )
        if ok:
            # Write apt list via shell tee (needs root).
            write_cmd = (
                f"echo '{repo_line}' | tee /etc/apt/sources.list.d/mullvad.list"
            )
            ok = run_as_root(["bash", "-lc", write_cmd], dry_run=dry_run)
        ok = run_as_root(["apt-get", "update"], dry_run=dry_run) and ok
        ok = run_as_root(
            ["apt-get", "install", "-y", "mullvad-vpn"],
            dry_run=dry_run,
        ) and ok
        return bool(detect_mullvad_vpn()) if not dry_run else ok

    if manager in {"dnf", "yum"}:
        if dry_run:
            log.info(
                "[DRY RUN] Would add Mullvad dnf repository and install mullvad-vpn"
            )
            return True
        ok = run_as_root(
            [
                manager,
                "config-manager",
                "addrepo",
                f"--from-repofile={MULLVAD_FEDORA_REPO}",
            ],
            dry_run=dry_run,
        )
        if not ok:
            ok = run_as_root(
                [
                    manager,
                    "config-manager",
                    "--add-repo",
                    MULLVAD_FEDORA_REPO,
                ],
                dry_run=dry_run,
            )
        ok = run_as_root(
            [manager, "install", "-y", "mullvad-vpn"],
            dry_run=dry_run,
        ) and ok
        return bool(detect_mullvad_vpn()) if not dry_run else ok

    log.warning(
        "Automatic Mullvad VPN install is not supported for this Linux "
        "package manager. See https://mullvad.net/en/download/vpn/linux"
    )
    return False


def ensure_proton_mail(dry_run: bool = False, update: bool = False) -> bool:
    detected = detect_proton_mail()
    if detected:
        if update and os.name == "nt":
            log.info(
                "Proton Mail found (%s). Updating because --update was requested...",
                detected,
            )
            return upgrade_package(WINGET_PROTON_MAIL, dry_run=dry_run)
        log.info(
            "Proton Mail already installed (%s). Skipping.",
            detected,
        )
        return True

    log.info("Proton Mail not found. Installing...")

    if os.name == "nt":
        return install_package(WINGET_PROTON_MAIL, dry_run=dry_run)

    manager = linux_package_manager()
    want_rpm = manager in {"dnf", "yum"}
    want_deb = manager == "apt-get"

    if want_deb or want_rpm:
        if dry_run:
            log.info(
                "[DRY RUN] Would download official Proton Mail %s and install it",
                "RPM" if want_rpm else "DEB",
            )
            return True

        try:
            with urllib.request.urlopen(
                PROTON_MAIL_VERSION_URL,
                timeout=30,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            log.error("Could not fetch Proton Mail version metadata: %s", exc)
            payload = None

        asset = None
        if payload:
            for release in payload.get("Releases", []):
                if release.get("CategoryName") != "Stable":
                    continue
                needle = ".rpm" if want_rpm else ".deb"
                for file_info in release.get("File", []):
                    identifier = str(file_info.get("Identifier", "")).lower()
                    url = file_info.get("Url")
                    checksum = file_info.get("Sha512CheckSum")
                    if needle in identifier and url and checksum:
                        asset = (url, checksum.lower())
                        break
                if asset:
                    break

        if asset:
            url, checksum = asset
            with tempfile.TemporaryDirectory() as tmp:
                suffix = ".rpm" if want_rpm else ".deb"
                package_path = Path(tmp) / f"ProtonMail-desktop{suffix}"
                if not download_file(url, package_path):
                    return False
                actual = sha512_file(package_path)
                if actual.lower() != checksum:
                    log.error(
                        "Proton Mail checksum mismatch "
                        "(expected %s, got %s)",
                        checksum,
                        actual,
                    )
                    return False
                if want_deb:
                    ok = run_as_root(
                        ["apt-get", "install", "-y", str(package_path)],
                        dry_run=dry_run,
                    )
                else:
                    ok = run_as_root(
                        [manager, "install", "-y", str(package_path)],
                        dry_run=dry_run,
                    )
                if ok and detect_proton_mail():
                    return True

    if command_exists("snap"):
        log.info("Trying Proton Mail via snap...")
        if dry_run:
            log.info("[DRY RUN] snap install proton-mail")
            return True
        try:
            result = run_command(
                ["sudo", "snap", "install", "proton-mail"]
                if hasattr(os, "geteuid") and os.geteuid() != 0
                else ["snap", "install", "proton-mail"],
                timeout=900,
                capture=False,
            )
            if result.returncode == 0 and detect_proton_mail():
                return True
        except Exception as exc:
            log.error("Snap Proton Mail install failed: %s", exc)

    log.warning(
        "Could not install Proton Mail automatically. "
        "Download from https://proton.me/support/set-up-proton-mail-linux"
    )
    return False


def ensure_privacy_stack(
    dry_run: bool = False,
    *,
    update: bool = False,
    install_browsers: bool = True,
    install_brave: bool = True,
    install_duckduckgo: bool = True,
    install_mullvad: bool = True,
    install_proton_mail: bool = True,
) -> bool:
    ok = True

    if install_browsers:
        if install_duckduckgo and install_brave:
            if not ensure_privacy_browsers(
                dry_run=dry_run,
                update=update,
            ):
                ok = False
        else:
            if install_duckduckgo and not ensure_duckduckgo(
                dry_run=dry_run,
                update=update,
            ):
                # Soft-fail on Linux is expected.
                if os.name == "nt":
                    ok = False
            if install_brave and not ensure_brave(
                dry_run=dry_run,
                update=update,
            ):
                ok = False

    if install_mullvad and not ensure_mullvad_vpn(
        dry_run=dry_run,
        update=update,
    ):
        ok = False

    if install_proton_mail and not ensure_proton_mail(
        dry_run=dry_run,
        update=update,
    ):
        ok = False

    return ok


# ============================================================================
# OLLAMA INSTALLATION
# ============================================================================


def ensure_ollama(
    dry_run: bool = False,
) -> bool:

    if command_exists("ollama"):
        log.info(
            "Ollama already installed: %s",
            command_version("ollama"),
        )
        return True

    if dry_run:
        log.info(
            "[DRY RUN] Ollama would be installed."
        )
        return True

    if os.name == "nt":
        manager = windows_package_manager()

        if manager == "winget":
            return install_package(
                "Ollama.Ollama",
                dry_run=dry_run,
            )

        if manager == "choco":
            return install_package(
                "ollama",
                dry_run=dry_run,
            )

        log.warning(
            "Ollama could not be installed automatically "
            "because no supported Windows package manager "
            "was found."
        )

        return False

    # Linux:
    #
    # Ollama publishes an official installation method. We only use it
    # when curl exists and the user has explicitly requested installation.
    if not command_exists("curl"):
        log.warning(
            "curl is required for automatic Ollama installation on Linux."
        )
        return False

    log.info(
        "Installing Ollama using the official Linux installer..."
    )

    try:
        result = subprocess.run(
            [
                "sh",
                "-c",
                "curl -fsSL https://ollama.com/install.sh | sh",
            ],
            timeout=900,
            capture_output=False,
            shell=False,
        )

        return result.returncode == 0

    except Exception as exc:
        log.error(
            "Ollama installation failed: %s",
            exc,
        )
        return False


# ============================================================================
# DOCKER
# ============================================================================


def docker_available() -> bool:
    return command_exists("docker")


def docker_running() -> bool:
    if not docker_available():
        return False

    try:
        result = run_command(
            [
                "docker",
                "info",
            ],
            timeout=30,
        )

        return result.returncode == 0

    except Exception:
        return False


def docker_compose_available() -> bool:
    if not docker_available():
        return False

    try:
        result = run_command(
            [
                "docker",
                "compose",
                "version",
            ],
            timeout=15,
        )

        return result.returncode == 0

    except Exception:
        return False


def ensure_docker(
    dry_run: bool = False,
) -> bool:

    if docker_available():
        if docker_compose_available():
            return True

        log.warning(
            "Docker exists but Docker Compose is unavailable."
        )

        return False

    if os.name == "nt":
        return install_package(
            "Docker.DockerDesktop",
            dry_run=dry_run,
        )

    log.warning(
        "Automatic Docker installation is intentionally "
        "distribution-specific on Linux."
    )

    log.warning(
        "Install Docker Engine using your distribution's "
        "official Docker instructions, then rerun."
    )

    return False


# ============================================================================
# LIBRECHAT
# ============================================================================


def is_librechat_checkout(path: Path) -> bool:
    if not path.is_dir():
        return False

    return (
        (path / "docker-compose.yml").exists()
        or (path / "docker-compose.yaml").exists()
    )


def librechat_search_paths() -> list[Path]:
    """
    Candidate LibreChat locations for discovery on existing machines.
    New installs still default to ~/LibreChat.
    """

    candidates: list[Path] = []

    for env_key in (
        "PRIVACY_AI_LIBRECHAT_DIR",
        "LLM_WORKSTATION_LIBRECHAT_DIR",
    ):
        value = os.environ.get(env_key)
        if value:
            candidates.append(Path(value))

    if LIBRECHAT_PATH_FILE.exists():
        try:
            remembered = LIBRECHAT_PATH_FILE.read_text(
                encoding="utf-8"
            ).strip()
            if remembered:
                candidates.append(Path(remembered))
        except OSError:
            pass

    candidates.extend(
        [
            DEFAULT_LIBRECHAT_DIR,
            Path.home() / "apps" / "LibreChat",
            Path.home() / "Documents" / "LibreChat",
            Path.home() / "source" / "LibreChat",
            Path.home() / "dev" / "LibreChat",
            Path.home() / "projects" / "LibreChat",
            Path("C:/AI Library/apps/LibreChat"),
            Path("/opt/LibreChat"),
            Path("/srv/LibreChat"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.expanduser())
        except OSError:
            key = str(path)
        lowered = key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(Path(key))

    return unique


def remember_librechat_dir(path: Path) -> None:
    try:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        LIBRECHAT_PATH_FILE.write_text(
            str(path.resolve()),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning(
            "Could not persist LibreChat path: %s",
            exc,
        )


def find_librechat_dir() -> Optional[Path]:
    for path in librechat_search_paths():
        try:
            if is_librechat_checkout(path):
                resolved = path.resolve()
                remember_librechat_dir(resolved)
                return resolved
        except OSError:
            continue
    return None


def get_librechat_dir() -> Path:
    found = find_librechat_dir()
    if found:
        return found
    return DEFAULT_LIBRECHAT_DIR


def librechat_exists() -> bool:
    return find_librechat_dir() is not None


def detect_librechat() -> Optional[str]:
    path = find_librechat_dir()
    if not path:
        return None

    health = "running" if librechat_health() else "installed"
    return f"{health} @ {path}"


def update_librechat_repository(
    path: Path,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Update an existing LibreChat checkout without touching user config files.
    """

    if dry_run:
        log.info(
            "[DRY RUN] Would git pull and docker compose pull in %s",
            path,
        )
        return True

    ok = True

    if (path / ".git").exists() and command_exists("git"):
        try:
            result = run_command(
                ["git", "pull", "--ff-only"],
                timeout=600,
                capture=False,
                cwd=path,
            )
            if result.returncode != 0:
                log.warning(
                    "git pull --ff-only failed in %s "
                    "(local changes may block updates).",
                    path,
                )
                ok = False
        except Exception as exc:
            log.warning("LibreChat git update failed: %s", exc)
            ok = False
    else:
        log.info(
            "LibreChat at %s is not a git checkout; skipping git pull.",
            path,
        )

    if docker_running():
        try:
            result = run_command(
                ["docker", "compose", "pull"],
                timeout=1800,
                capture=False,
                cwd=path,
            )
            if result.returncode != 0:
                log.warning("docker compose pull failed for LibreChat.")
                ok = False
        except Exception as exc:
            log.warning("LibreChat image pull failed: %s", exc)
            ok = False

    return ok


def ensure_librechat_repository(
    dry_run: bool = False,
    update: bool = False,
) -> bool:

    existing = find_librechat_dir()
    if existing:
        log.info(
            "LibreChat already exists at %s. Skipping clone.",
            existing,
        )
        if update:
            log.info(
                "Updating LibreChat because --update was requested..."
            )
            return update_librechat_repository(
                existing,
                dry_run=dry_run,
            )
        return True

    target = DEFAULT_LIBRECHAT_DIR

    if not command_exists("git"):
        log.error(
            "Git is required for LibreChat."
        )
        return False

    log.info(
        "LibreChat not found. Cloning into %s ...",
        target,
    )

    if dry_run:
        log.info(
            "[DRY RUN] Would clone LibreChat into %s",
            target,
        )
        return True

    if target.exists() and not is_librechat_checkout(target):
        log.error(
            "Path %s exists but is not a LibreChat checkout.",
            target,
        )
        return False

    try:
        result = run_command(
            [
                "git",
                "clone",
                "--depth",
                "1",
                LIBRECHAT_REPO,
                str(target),
            ],
            timeout=900,
            capture=False,
        )

        if result.returncode != 0:
            return False

        if is_librechat_checkout(target):
            remember_librechat_dir(target)
            return True

        return False

    except Exception as exc:
        log.error(
            "LibreChat clone failed: %s",
            exc,
        )
        return False


def _upsert_env_key(text: str, key: str, value: str) -> str:
    """
    Set KEY=value in a dotenv-style file.
    Replaces an existing assignment (commented or not); otherwise appends.
    """

    pattern = re.compile(
        rf"^[ \t]*#?[ \t]*{re.escape(key)}[ \t]*=.*$",
        re.MULTILINE,
    )
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + f"\n# Privacy AI Workstation\n{line}\n"


def patch_librechat_env_linux(env_path: Path) -> bool:
    """
    Apply Linux/Docker Compose hostname + UID/GID fixes to LibreChat .env.

    Upstream .env.example defaults MONGO_URI/MEILI_HOST to localhost-style
    values that break when the app reads .env inside Compose. Containers also
    need UID/GID matching the host user for bind mounts.
    """

    if os.name == "nt":
        return True

    try:
        text = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Could not read LibreChat .env: %s", exc)
        return False

    uid, gid = _linux_uid_gid()
    updates = {
        "MONGO_URI": "mongodb://mongodb:27017/LibreChat",
        "MEILI_HOST": "http://meilisearch:7700",
        "HOST": "0.0.0.0",
        "DOMAIN_CLIENT": "http://localhost:3080",
        "DOMAIN_SERVER": "http://localhost:3080",
    }
    if uid and gid:
        updates["UID"] = uid
        updates["GID"] = gid

    original = text
    for key, value in updates.items():
        text = _upsert_env_key(text, key, value)

    if text == original:
        return True

    try:
        env_path.write_text(text, encoding="utf-8")
        log.info(
            "Patched LibreChat .env for Docker Compose on Linux "
            "(service hostnames + UID/GID)."
        )
        return True
    except OSError as exc:
        log.error("Could not write LibreChat .env: %s", exc)
        return False


def prepare_librechat_data_dirs(librechat_dir: Path) -> bool:
    """
    Create common LibreChat bind-mount directories and best-effort chown on Linux.
    """

    meili_dirs = sorted(librechat_dir.glob("meili_data*"))
    targets = [
        librechat_dir / "data-node",
        librechat_dir / "images",
        librechat_dir / "uploads",
        librechat_dir / "logs",
        *meili_dirs,
    ]
    # Ensure at least one meili data dir name exists even before first pull.
    if not meili_dirs:
        targets.append(librechat_dir / "meili_data")

    for path in targets:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("Could not create %s: %s", path, exc)

    if os.name == "nt":
        return True

    uid, gid = _linux_uid_gid()
    if not uid or not gid:
        return True

    # Prefer plain chown when we own the tree; fall back to sudo.
    paths = [str(p) for p in targets if p.exists()]
    if not paths:
        return True

    try:
        result = run_command(
            ["chown", "-R", f"{uid}:{gid}", *paths],
            timeout=120,
        )
        if result.returncode == 0:
            log.info("Set LibreChat data directory ownership to %s:%s", uid, gid)
            return True
    except Exception:
        pass

    if command_exists("sudo"):
        try:
            result = run_command(
                ["sudo", "chown", "-R", f"{uid}:{gid}", *paths],
                timeout=120,
            )
            if result.returncode == 0:
                log.info(
                    "Set LibreChat data directory ownership to %s:%s (via sudo)",
                    uid,
                    gid,
                )
                return True
        except Exception as exc:
            log.warning("sudo chown for LibreChat data dirs failed: %s", exc)

    log.warning(
        "Could not chown LibreChat data dirs. If Meili/Mongo fail with "
        "permission errors, run: sudo chown -R %s:%s data-node images uploads "
        "logs meili_data*  (from the LibreChat directory).",
        uid,
        gid,
    )
    return True


def create_librechat_env(
    overwrite: bool = False,
) -> bool:

    librechat_dir = get_librechat_dir()

    example = librechat_dir / ".env.example"
    target = librechat_dir / ".env"

    if not example.exists():
        log.warning(
            ".env.example not found."
        )
        return False

    created = False
    try:
        if target.exists() and not overwrite:
            log.info("Existing LibreChat .env preserved.")
        else:
            shutil.copyfile(example, target)
            created = True
    except Exception as exc:
        log.error(
            "Could not create .env: %s",
            exc,
        )
        return False

    # Always apply Linux Docker hostname / UID patches (idempotent upserts).
    if os.name != "nt":
        if not patch_librechat_env_linux(target):
            return False
    elif created:
        pass

    return True


def configure_librechat_ollama() -> bool:
    """
    Configures an Ollama custom endpoint and mounts it into the API
    container through Docker Compose override.

    We preserve an existing configuration instead of overwriting it.
    On Linux, ensure host.docker.internal resolves via host-gateway.
    """

    librechat_dir = get_librechat_dir()
    if not is_librechat_checkout(librechat_dir):
        log.error("LibreChat is not installed.")
        return False

    config = librechat_dir / "librechat.yaml"
    override = librechat_dir / "docker-compose.override.yml"

    if config.exists():
        log.info(
            "Existing librechat.yaml preserved."
        )
    else:
        config.write_text(
            """\
version: 1.3.5
cache: true

endpoints:
  custom:
    - name: "Ollama"
      apiKey: "ollama"
      baseURL: "http://host.docker.internal:11434/v1/"
      models:
        default:
          - "qwen3:8b"
        fetch: true
      titleConvo: true
      modelDisplayLabel: "Ollama"
""",
            encoding="utf-8",
        )

    desired = """\
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./librechat.yaml:/app/librechat.yaml
"""

    if override.exists():
        text = override.read_text(
            encoding="utf-8",
            errors="replace",
        )

        has_mount = "/app/librechat.yaml" in text
        has_host = "host.docker.internal:host-gateway" in text

        if has_mount and (has_host or os.name == "nt"):
            return True

        if has_mount and not has_host and os.name != "nt":
            log.warning(
                "Existing docker-compose.override.yml mounts librechat.yaml "
                "but is missing host.docker.internal:host-gateway. "
                "Add that under services.api.extra_hosts if Ollama is unreachable."
            )
            return True

        log.warning(
            "Existing docker-compose.override.yml detected."
        )

        log.warning(
            "It was not modified automatically."
        )

        return True

    override.write_text(desired, encoding="utf-8")
    return True


def wait_for_librechat(timeout: int = 120) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if librechat_health():
            return True
        time.sleep(2)
    return False


def start_librechat() -> bool:
    librechat_dir = find_librechat_dir()
    if not librechat_dir:
        log.error(
            "LibreChat is not installed."
        )
        return False

    if not docker_running():
        log.error(
            "Docker is not running."
        )
        return False

    # Best-effort: Ollama should be up so the UI can list local models.
    ensure_ollama_running(timeout=45)

    if not create_librechat_env(overwrite=False):
        log.warning("LibreChat .env could not be fully prepared.")
    configure_librechat_ollama()
    prepare_librechat_data_dirs(librechat_dir)

    try:
        result = run_command(
            [
                "docker",
                "compose",
                "up",
                "-d",
            ],
            timeout=1800,
            capture=False,
            cwd=librechat_dir,
        )

        if result.returncode != 0:
            log.error("docker compose up failed for LibreChat.")
            return False

        log.info("Waiting for LibreChat at %s ...", LIBRECHAT_URL)
        if wait_for_librechat(timeout=180):
            log.info("LibreChat is responding at %s", LIBRECHAT_URL)
            return True

        log.error(
            "LibreChat containers were started but %s did not answer "
            "within 180s. Check: docker compose -f %s/docker-compose.yml ps "
            "and docker compose logs (mongodb / meilisearch / api). "
            "On Linux, permission issues on data-node/meili_data* are common; "
            "nested Docker with the vfs storage driver is also fragile.",
            LIBRECHAT_URL,
            librechat_dir,
        )
        return False

    except Exception as exc:
        log.error(
            "LibreChat start failed: %s",
            exc,
        )
        return False


def stop_librechat() -> bool:
    librechat_dir = find_librechat_dir()
    if not librechat_dir:
        return True

    try:
        result = run_command(
            [
                "docker",
                "compose",
                "down",
            ],
            timeout=300,
            capture=False,
            cwd=librechat_dir,
        )

        return result.returncode == 0

    except Exception as exc:
        log.error(
            "LibreChat stop failed: %s",
            exc,
        )
        return False


def librechat_health() -> bool:
    try:
        request = urllib.request.Request(
            LIBRECHAT_URL,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:

            return 200 <= response.status < 500

    except Exception:
        return False


# ============================================================================
# MODEL DOWNLOAD
# ============================================================================


def pull_model(
    model: str,
) -> bool:

    if not command_exists("ollama"):
        log.error(
            "Ollama is not installed."
        )
        return False

    if not ollama_api_available():
        if not ensure_ollama_running(timeout=60):
            log.error(
                "Ollama is installed but the API is not responding at %s. "
                "Start Ollama (`ollama serve` or your service manager), then retry.",
                OLLAMA_URL,
            )
            return False

    log.info(
        "Pulling model: %s",
        model,
    )

    try:
        result = run_command(
            [
                "ollama",
                "pull",
                model,
            ],
            timeout=7200,
            capture=False,
        )

        return result.returncode == 0

    except Exception as exc:
        log.error(
            "Model download failed: %s",
            exc,
        )
        return False


# ============================================================================
# REPORTING
# ============================================================================


def print_hardware(
    hardware: Hardware,
) -> None:

    print()
    print("=" * 76)
    print(" HARDWARE")
    print("=" * 76)

    print(
        f"OS:             {hardware.os} "
        f"{hardware.os_version}"
    )

    print(
        f"Architecture:   {hardware.architecture}"
    )

    print(
        f"CPU:            {hardware.cpu}"
    )

    print(
        f"CPU threads:    {hardware.cpu_threads}"
    )

    print(
        f"RAM:            {gb(hardware.ram_total_gb)} "
        f"(available {gb(hardware.ram_available_gb)})"
    )

    print(
        f"Disk:           {gb(hardware.disk_free_gb)} free "
        f"/ {gb(hardware.disk_total_gb)}"
    )

    print(
        f"Virtualized:    {hardware.virtualization}"
    )

    print(
        f"Administrator:  {hardware.is_admin}"
    )

    print()
    print("GPUs")

    if not hardware.gpus:
        print(
            "  No dedicated GPU detected."
        )

    for gpu in hardware.gpus:
        print(
            f"  GPU {gpu.index}: "
            f"{gpu.vendor} {gpu.name}"
        )

        print(
            f"      VRAM:    {gb(gpu.vram_gb)}"
        )

        print(
            f"      Backend: {gpu.backend or 'unknown'}"
        )

        if gpu.driver:
            print(
                f"      Driver:  {gpu.driver}"
            )

        if gpu.compute_capability:
            print(
                f"      CUDA:    {gpu.compute_capability}"
            )


def print_software(
    software: Software,
) -> None:

    print()
    print("=" * 76)
    print(" SOFTWARE")
    print("=" * 76)

    core_keys = (
        "python",
        "git",
        "node",
        "npm",
        "docker",
        "docker_compose",
        "ollama",
        "vscodium",
        "librechat",
    )
    privacy_keys = (
        "brave",
        "duckduckgo",
        "mullvad_vpn",
        "proton_mail",
    )
    values = asdict(software)

    core_labels = {
        "docker_compose": "Docker Compose",
        "vscodium": "VSCodium",
        "librechat": "LibreChat",
    }
    for key in core_keys:
        label = core_labels.get(
            key,
            key.replace("_", " ").title(),
        )
        print(
            f"{label:20}: "
            f"{values.get(key) or 'NOT INSTALLED'}"
        )

    print()
    print("=" * 76)
    print(" PRIVACY APPS")
    print("=" * 76)

    privacy_labels = {
        "brave": "Brave",
        "duckduckgo": "DuckDuckGo",
        "mullvad_vpn": "Mullvad VPN",
        "proton_mail": "Proton Mail",
    }
    for key in privacy_keys:
        label = privacy_labels.get(key, key.replace("_", " ").title())
        print(
            f"{label:20}: "
            f"{values.get(key) or 'NOT INSTALLED'}"
        )


def print_recommendations(
    hardware: Hardware,
) -> None:

    print()
    print("=" * 76)
    print(" MODEL COMPATIBILITY")
    print("=" * 76)

    results = recommended_catalog(
        hardware
    )

    for result in results:

        status = result["status"]

        if status == "FULL_GPU":
            icon = "OK"

        elif status in {
            "HYBRID",
            "CPU_OR_OFFLOAD",
        }:
            icon = "MAYBE"

        elif status == "INSUFFICIENT_DISK":
            icon = "DISK"

        else:
            icon = "NO"

        print(
            f"{icon:6} "
            f"{result['model']:20} "
            f"{result.get('estimated_runtime_gb', '?')} GB "
            f"| {status}"
        )

        print(
            f"       {result.get('reason', '')}"
        )


def print_installed_models() -> None:
    models = ollama_models()

    print()
    print("=" * 76)
    print(" INSTALLED OLLAMA MODELS")
    print("=" * 76)

    if not models:
        print(
            "No models detected or Ollama is unavailable."
        )
        return

    for model in models:
        name = model.get(
            "name",
            "unknown",
        )

        size = model.get(
            "size"
        )

        size_text = (
            gb(
                size / (1024 ** 3)
            )
            if size
            else "unknown"
        )

        print(
            f"{name:30} {size_text}"
        )


def save_report(
    hardware: Hardware,
    software: Software,
) -> None:

    BASE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "application": {
            "name": APP_NAME,
            "version": APP_VERSION,
        },

        "timestamp_utc": datetime_module.datetime.now(
            datetime_module.timezone.utc
        ).isoformat(),

        "hardware": asdict(
            hardware
        ),

        "software": asdict(
            software
        ),

        "model_analysis": recommended_catalog(
            hardware
        ),

        "ollama_models": (
            ollama_models()
            if ollama_api_available()
            else []
        ),
    }

    REPORT_FILE.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info(
        "Report written to %s",
        REPORT_FILE,
    )


# ============================================================================
# STATUS
# ============================================================================


def status(
    hardware: Hardware,
    software: Software,
) -> None:

    print_hardware(
        hardware
    )

    print_software(
        software
    )

    print()
    print("=" * 76)
    print(" SERVICES")
    print("=" * 76)

    print(
        f"Ollama API:       "
        f"{'RUNNING' if ollama_api_available() else 'NOT RUNNING'}"
    )

    print(
        f"Docker daemon:    "
        f"{'RUNNING' if docker_running() else 'NOT RUNNING'}"
    )

    librechat_dir = find_librechat_dir()
    if librechat_dir:
        state = "RUNNING" if librechat_health() else "INSTALLED (not running)"
        print(
            f"LibreChat:        {state}"
        )
        print(
            f"LibreChat path:   {librechat_dir}"
        )
    else:
        print(
            "LibreChat:        NOT INSTALLED"
        )

    print_recommendations(
        hardware
    )


# ============================================================================
# INSTALLATION
# ============================================================================


def install(
    args: argparse.Namespace,
) -> int:

    hardware = audit_hardware()

    print_hardware(
        hardware
    )

    print()
    print(
        "The installer will configure a privacy-focused local AI workstation."
    )
    print(
        "Behavior: scan each component → install if missing → "
        "skip if healthy."
    )
    if getattr(args, "update", False):
        print(
            "Update mode: already-installed components will be upgraded."
        )
    else:
        print(
            "Tip: pass --update to upgrade components that are already present."
        )
    print(
        "It will NOT automatically download an LLM "
        "unless --model / --pull-model is supplied."
    )
    print(
        "VPN and email apps are installed only; account login stays manual."
    )

    if not args.yes:
        if not ask_yes_no(
            "Continue with workstation installation?",
            default=True,
        ):
            return 0

    # ------------------------------------------------------------------
    # Git
    # ------------------------------------------------------------------

    log.info(
        "[1/8] Checking Git..."
    )

    update = bool(getattr(args, "update", False))
    failures: list[str] = []

    def record(step: str, ok: bool) -> None:
        if not ok:
            failures.append(step)
            log.error("Step failed: %s", step)

    if not ensure_git(dry_run=args.dry_run):
        record("git", False)

    # ------------------------------------------------------------------
    # Node
    # ------------------------------------------------------------------

    log.info(
        "[2/8] Checking Node.js..."
    )

    if not ensure_node(dry_run=args.dry_run):
        record("node", False)

    # ------------------------------------------------------------------
    # VSCodium
    # ------------------------------------------------------------------

    if not args.no_vscodium:
        log.info(
            "[3/8] Checking VSCodium..."
        )

        if not ensure_vscodium(dry_run=args.dry_run):
            # Optional editor — warn but do not fail the whole install.
            log.warning("VSCodium could not be ensured (optional).")

    # ------------------------------------------------------------------
    # Privacy stack
    # ------------------------------------------------------------------

    if not args.no_privacy:
        log.info(
            "[4/8] Checking privacy apps "
            "(DuckDuckGo, Brave, Mullvad VPN, Proton Mail)..."
        )

        if not ensure_privacy_stack(
            dry_run=args.dry_run,
            update=update,
            install_browsers=True,
            install_brave=not args.no_brave,
            install_duckduckgo=not args.no_duckduckgo,
            install_mullvad=not args.no_mullvad,
            install_proton_mail=not args.no_proton_mail,
        ):
            record("privacy-stack", False)

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    log.info(
        "[5/8] Checking Ollama..."
    )

    if not ensure_ollama(dry_run=args.dry_run):
        record("ollama", False)
    elif not args.dry_run:
        # Install alone does not always leave the API listening (esp. Linux
        # without systemd). Start it so later model pulls / LibreChat work.
        if not ensure_ollama_running(dry_run=False):
            log.warning(
                "Ollama is installed but the API is not running yet. "
                "Start it with `ollama serve` (or your service manager) before "
                "pulling models or using LibreChat."
            )

    # ------------------------------------------------------------------
    # Docker
    # ------------------------------------------------------------------

    if not args.no_docker:

        log.info(
            "[6/8] Checking Docker..."
        )

        if not ensure_docker(dry_run=args.dry_run):
            # LibreChat needs Docker; treat as failure unless LibreChat skipped.
            if args.no_librechat:
                log.warning("Docker could not be ensured.")
            else:
                record("docker", False)

    # ------------------------------------------------------------------
    # LibreChat
    # ------------------------------------------------------------------

    if not args.no_librechat:

        log.info(
            "[7/8] Setting up LibreChat..."
        )

        if docker_available() or args.dry_run:
            if ensure_librechat_repository(
                dry_run=args.dry_run,
                update=update,
            ):
                if not args.dry_run:
                    create_librechat_env()
                    configure_librechat_ollama()
                    prepare_librechat_data_dirs(get_librechat_dir())
                    if os.name != "nt":
                        log.info(
                            "Linux LibreChat notes: .env patched for Compose "
                            "service hostnames + UID/GID; data dirs prepared; "
                            "override adds host.docker.internal:host-gateway. "
                            "Docker Engine is still manual on Linux. Nested "
                            "Docker/vfs environments may still fail Meili/Mongo. "
                            "See docs/platforms.md."
                        )
            else:
                record("librechat", False)
        else:
            log.error(
                "Docker is required for LibreChat and is not available."
            )
            record("librechat-docker", False)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    log.info(
        "[8/8] Generating final report..."
    )

    software = audit_software()

    save_report(
        hardware,
        software,
    )

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    if args.model:

        result = classify_model(
            hardware,
            args.model,
        )

        print()
        print(
            f"Requested model: {args.model}"
        )

        print(
            f"Status:          {result['status']}"
        )

        print(
            f"Estimated memory: "
            f"{result.get('estimated_runtime_gb', '?')} GB"
        )

        print(
            f"Reason:           "
            f"{result.get('reason', '')}"
        )

        if result["status"] in {
            "NOT_RECOMMENDED",
            "INSUFFICIENT_DISK",
        }:

            log.warning(
                "The requested model does not fit the "
                "conservative hardware profile."
            )

            if not args.yes:
                if not ask_yes_no(
                    "Download it anyway?",
                    default=False,
                ):
                    return 1 if failures else 0

        if (
            args.pull_model
            or args.yes
        ):
            if not pull_model(
                args.model
            ):
                record("model-pull", False)

    elif args.pull_model:

        recommendations = recommended_catalog(
            hardware
        )

        compatible = [
            item
            for item in recommendations
            if item["status"]
            in {
                "FULL_GPU",
                "HYBRID",
                "CPU_OR_OFFLOAD",
            }
        ]

        if compatible:

            # Prefer full-GPU models, then hybrid/offload.
            model = compatible[0]["model"]

            print()
            print(
                f"Recommended automatic model: {model}"
            )

            if args.yes or ask_yes_no(
                f"Download {model}?",
                default=False,
            ):
                if not pull_model(model):
                    record("model-pull", False)

    # ------------------------------------------------------------------
    # Start LibreChat
    # ------------------------------------------------------------------

    if (
        not args.no_librechat
        and docker_running()
        and librechat_exists()
    ):

        if args.start:
            if start_librechat():
                log.info(
                    "LibreChat started."
                )
            else:
                record("librechat-start", False)

    if failures:
        print()
        log.error(
            "Install finished with failures: %s",
            ", ".join(failures),
        )
        return 1

    log.info("Install finished successfully.")
    return 0


# ============================================================================
# REPAIR
# ============================================================================


def repair(
    args: argparse.Namespace,
) -> int:

    hardware = audit_hardware()
    failures: list[str] = []

    log.info(
        "Running repair operation..."
    )

    update = bool(getattr(args, "update", False))

    if not command_exists("git"):
        if not ensure_git(dry_run=args.dry_run):
            failures.append("git")

    if not command_exists("node"):
        if not ensure_node(dry_run=args.dry_run):
            failures.append("node")

    if not command_exists("ollama"):
        if not ensure_ollama(dry_run=args.dry_run):
            failures.append("ollama")
    elif not args.dry_run:
        ensure_ollama_running(dry_run=False)

    if not getattr(args, "no_privacy", False):
        if not ensure_privacy_stack(
            dry_run=args.dry_run,
            update=update,
            install_browsers=True,
            install_brave=not getattr(args, "no_brave", False),
            install_duckduckgo=not getattr(args, "no_duckduckgo", False),
            install_mullvad=not getattr(args, "no_mullvad", False),
            install_proton_mail=not getattr(args, "no_proton_mail", False),
        ):
            failures.append("privacy-stack")

    if not args.no_docker:
        if not docker_available():
            if not ensure_docker(dry_run=args.dry_run):
                if not args.no_librechat:
                    failures.append("docker")

    if (
        not args.no_librechat
        and (docker_available() or args.dry_run)
    ):
        if not ensure_librechat_repository(
            dry_run=args.dry_run,
            update=update,
        ):
            failures.append("librechat")
        elif not args.dry_run:
            create_librechat_env()
            configure_librechat_ollama()
            prepare_librechat_data_dirs(get_librechat_dir())

    software = audit_software()

    save_report(
        hardware,
        software,
    )

    if failures:
        log.error(
            "Repair finished with failures: %s",
            ", ".join(failures),
        )
        return 1

    log.info("Repair finished successfully.")
    return 0


# ============================================================================
# ARGUMENTS
# ============================================================================


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=APP_NAME
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # audit
    audit_parser = subparsers.add_parser(
        "audit",
        help="Scan hardware and software.",
    )

    # status
    subparsers.add_parser(
        "status",
        help="Show current workstation status.",
    )

    # report
    subparsers.add_parser(
        "report",
        help="Generate JSON hardware/software report.",
    )

    # models
    subparsers.add_parser(
        "models",
        help="Show installed Ollama models.",
    )

    # install
    install_parser = subparsers.add_parser(
        "install",
        help="Install/configure the privacy AI workstation.",
    )

    install_parser.add_argument(
        "--model",
        help="Specific Ollama model to download.",
    )

    install_parser.add_argument(
        "--pull-model",
        action="store_true",
        help="Automatically download the recommended model.",
    )

    install_parser.add_argument(
        "--start",
        action="store_true",
        help="Start LibreChat after installation.",
    )

    install_parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive mode.",
    )

    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify the system.",
    )

    install_parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "Also upgrade components that are already installed "
            "(default is skip-if-healthy)."
        ),
    )

    install_parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Skip Docker.",
    )

    install_parser.add_argument(
        "--no-librechat",
        action="store_true",
        help="Skip LibreChat.",
    )

    install_parser.add_argument(
        "--no-vscodium",
        action="store_true",
        help="Skip VSCodium.",
    )

    install_parser.add_argument(
        "--no-privacy",
        action="store_true",
        help="Skip privacy apps (browsers, Mullvad, Proton Mail).",
    )

    install_parser.add_argument(
        "--no-brave",
        action="store_true",
        help="Skip Brave browser.",
    )

    install_parser.add_argument(
        "--no-duckduckgo",
        action="store_true",
        help="Skip DuckDuckGo browser.",
    )

    install_parser.add_argument(
        "--no-mullvad",
        action="store_true",
        help="Skip Mullvad VPN.",
    )

    install_parser.add_argument(
        "--no-proton-mail",
        action="store_true",
        help="Skip Proton Mail.",
    )

    # repair
    repair_parser = subparsers.add_parser(
        "repair",
        help="Repair missing/broken components.",
    )

    repair_parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    repair_parser.add_argument(
        "--update",
        action="store_true",
        help="Upgrade installed components while repairing.",
    )

    repair_parser.add_argument(
        "--no-docker",
        action="store_true",
    )

    repair_parser.add_argument(
        "--no-librechat",
        action="store_true",
    )

    repair_parser.add_argument(
        "--no-privacy",
        action="store_true",
        help="Skip privacy apps.",
    )

    repair_parser.add_argument(
        "--no-brave",
        action="store_true",
    )

    repair_parser.add_argument(
        "--no-duckduckgo",
        action="store_true",
    )

    repair_parser.add_argument(
        "--no-mullvad",
        action="store_true",
    )

    repair_parser.add_argument(
        "--no-proton-mail",
        action="store_true",
    )

    # start
    subparsers.add_parser(
        "start",
        help="Start LibreChat.",
    )

    # stop
    subparsers.add_parser(
        "stop",
        help="Stop LibreChat.",
    )

    return parser.parse_args()


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    args = parse_args()

    if sys.version_info < MIN_PYTHON:
        print(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} "
            "or newer is required."
        )
        return 2

    if platform.system() not in {
        "Windows",
        "Linux",
    }:
        print(
            "This release supports Windows and Linux."
        )
        return 2

    log.info(
        "%s %s starting",
        APP_NAME,
        APP_VERSION,
    )

    # --------------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------------

    if args.command == "audit":

        hardware = audit_hardware()
        software = audit_software()

        print_hardware(
            hardware
        )

        print_software(
            software
        )

        print_recommendations(
            hardware
        )

        save_report(
            hardware,
            software,
        )

        return 0

    # --------------------------------------------------------------
    # STATUS
    # --------------------------------------------------------------

    if args.command == "status":

        hardware = audit_hardware()
        software = audit_software()

        status(
            hardware,
            software,
        )

        return 0

    # --------------------------------------------------------------
    # REPORT
    # --------------------------------------------------------------

    if args.command == "report":

        hardware = audit_hardware()
        software = audit_software()

        save_report(
            hardware,
            software,
        )

        print(
            f"Report: {REPORT_FILE}"
        )

        return 0

    # --------------------------------------------------------------
    # MODELS
    # --------------------------------------------------------------

    if args.command == "models":

        print_installed_models()

        return 0

    # --------------------------------------------------------------
    # INSTALL
    # --------------------------------------------------------------

    if args.command == "install":
        return install(
            args
        )

    # --------------------------------------------------------------
    # REPAIR
    # --------------------------------------------------------------

    if args.command == "repair":
        return repair(
            args
        )

    # --------------------------------------------------------------
    # START
    # --------------------------------------------------------------

    if args.command == "start":

        if start_librechat():
            print(
                f"LibreChat should be available at "
                f"{LIBRECHAT_URL}"
            )

            return 0

        return 1

    # --------------------------------------------------------------
    # STOP
    # --------------------------------------------------------------

    if args.command == "stop":

        return (
            0
            if stop_librechat()
            else 1
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:
        log.warning(
            "Interrupted by user."
        )

        raise SystemExit(130)

    except Exception as exc:
        log.exception(
            "Fatal error: %s",
            exc,
        )

        print()
        print(
            f"Fatal error: {exc}"
        )

        print(
            f"See log: {LOG_FILE}"
        )

        raise SystemExit(1)
