#!/usr/bin/env bash
# install.sh — thin wrapper around install.py for Linux/macOS users.
# Windows users: run `python install.py` directly.
#
# This is kept for backward compat with anyone using the old shell installer.
# The real logic lives in install.py — that's what ComfyUI Manager will run.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.9+ first." >&2
    exit 1
fi

exec "$PY" "$SOURCE/install.py" "$@"
