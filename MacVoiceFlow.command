#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  "$ROOT_DIR/scripts/install.sh"
fi

exec "$ROOT_DIR/scripts/run.sh"
