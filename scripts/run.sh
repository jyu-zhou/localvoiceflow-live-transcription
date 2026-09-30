#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "尚未安装 MacVoiceFlow，请先运行 ./scripts/install.sh。"
  exit 1
fi

export MACVOICEFLOW_CACHE_DIR="${MACVOICEFLOW_CACHE_DIR:-$HOME/Library/Caches/MacVoiceFlow}"
export HF_HOME="${HF_HOME:-$MACVOICEFLOW_CACHE_DIR/huggingface}"
export PATH="/opt/homebrew/bin:${PATH:-}"

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/src/macvoiceflow/realtime_app.py" "$@"
