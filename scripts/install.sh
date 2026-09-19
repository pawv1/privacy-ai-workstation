#!/usr/bin/env bash
# Privacy AI Workstation — Linux helper
# Usage:
#   ./scripts/install.sh
#   ./scripts/install.sh audit
#   ./scripts/install.sh install --update --yes
#
# If Python is missing, use ./scripts/bootstrap.sh instead.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/privacy-ai-workstation.py"

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

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && version_ok "$candidate"; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "Python 3.10+ was not found." >&2
  echo "Use the bootstrap script to install Python, then continue:" >&2
  echo "  ./scripts/bootstrap.sh" >&2
  echo "Or download Python from:" >&2
  echo "  https://www.python.org/downloads/" >&2
  exit 1
fi

if [[ "$#" -eq 0 ]]; then
  set -- install
fi

exec "$PYTHON" "$SCRIPT" "$@"
