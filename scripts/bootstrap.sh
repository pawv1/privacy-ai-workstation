#!/usr/bin/env bash
# Privacy AI Workstation — Linux bootstrap
# Installs Python 3 (if needed) via the system package manager, then runs the CLI.
#
# Usage:
#   chmod +x scripts/bootstrap.sh
#   ./scripts/bootstrap.sh
#   ./scripts/bootstrap.sh audit
#   ./scripts/bootstrap.sh install --yes --start
#
# Manual Python download / docs:
#   https://www.python.org/downloads/

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/privacy-ai-workstation.py"
MIN_MAJOR=3
MIN_MINOR=10
PYTHON_DOWNLOADS="https://www.python.org/downloads/"

if [[ ! -f "$SCRIPT" ]]; then
  echo "Could not find privacy-ai-workstation.py at $SCRIPT" >&2
  exit 1
fi

version_ok() {
  local exe="$1"
  "$exe" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if version_ok "$candidate"; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

install_python() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
    return $?
  fi
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip
    return $?
  fi
  if command -v yum >/dev/null 2>&1; then
    sudo yum install -y python3 python3-pip
    return $?
  fi
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python python-pip
    return $?
  fi
  if command -v zypper >/dev/null 2>&1; then
    sudo zypper --non-interactive install python3 python3-pip
    return $?
  fi
  if command -v apk >/dev/null 2>&1; then
    sudo apk add python3 py3-pip
    return $?
  fi
  return 1
}

echo "Privacy AI Workstation bootstrap"
echo "Checking for Python ${MIN_MAJOR}.${MIN_MINOR}+ ..."

PYTHON_EXE="$(find_python || true)"
if [[ -z "${PYTHON_EXE}" ]]; then
  echo "Python ${MIN_MAJOR}.${MIN_MINOR}+ not found."
  echo "Attempting system package install..."
  if ! install_python; then
    echo "Could not install Python automatically." >&2
    echo "Install Python ${MIN_MAJOR}.${MIN_MINOR}+ manually, then re-run:" >&2
    echo "  $PYTHON_DOWNLOADS" >&2
    exit 1
  fi
  PYTHON_EXE="$(find_python || true)"
  if [[ -z "${PYTHON_EXE}" ]]; then
    echo "Python was installed but is not on PATH yet. Open a new shell and re-run." >&2
    exit 1
  fi
fi

echo "Using Python: $PYTHON_EXE"
"$PYTHON_EXE" --version

if [[ "$#" -eq 0 ]]; then
  set -- install
fi

echo "Running: privacy-ai-workstation.py $*"
exec "$PYTHON_EXE" "$SCRIPT" "$@"
