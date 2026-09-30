#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "尚未安装 LocalVoiceFlow，请先运行 ./scripts/install.sh。"
  exit 1
fi

if ! "$ROOT_DIR/.venv/bin/python" -c 'import tkinter' >/dev/null 2>&1; then
  echo "LocalVoiceFlow 的本地 Python 环境缺少 tkinter，请重新运行 ./scripts/install.sh。"
  exit 1
fi

if [[ -z "${LOCALVOICEFLOW_CACHE_DIR:-}" && -z "${MACVOICEFLOW_CACHE_DIR:-}" ]]; then
  if [[ -d "$HOME/Library/Caches/MacVoiceFlow" && ! -d "$HOME/Library/Caches/LocalVoiceFlow" ]]; then
    export MACVOICEFLOW_CACHE_DIR="$HOME/Library/Caches/MacVoiceFlow"
  else
    export LOCALVOICEFLOW_CACHE_DIR="$HOME/Library/Caches/LocalVoiceFlow"
  fi
fi
export LOCALVOICEFLOW_CACHE_DIR="${LOCALVOICEFLOW_CACHE_DIR:-${MACVOICEFLOW_CACHE_DIR:-$HOME/Library/Caches/LocalVoiceFlow}}"
export HF_HOME="${HF_HOME:-$LOCALVOICEFLOW_CACHE_DIR/huggingface}"
export PATH="/opt/homebrew/bin:${PATH:-}"

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/src/macvoiceflow/realtime_app.py" "$@"
