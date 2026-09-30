#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "MacVoiceFlow 目前只支持 macOS。"
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "MacVoiceFlow 依赖 Apple Silicon 的 MLX，目前只支持 arm64。"
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "未找到 python3。请先安装 Python 3.11，然后重新运行。"
  exit 1
fi

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_VERSION" != "3.11" && "$PYTHON_VERSION" != "3.12" ]]; then
  echo "需要 Python 3.11 或 3.12；当前是 Python $PYTHON_VERSION。"
  echo "可用 PYTHON_BIN=/path/to/python3 ./scripts/install.sh 指定解释器。"
  exit 1
fi

echo "使用 Python $PYTHON_VERSION 创建本地环境..."
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/requirements-macos.txt"

mkdir -p "$HOME/Documents/MacVoiceFlow" "$HOME/Library/Caches/MacVoiceFlow/huggingface"

echo
echo "MacVoiceFlow 安装完成。"
echo "下一步：双击 MacVoiceFlow.command，或运行 ./scripts/run.sh"
echo "首次启动会下载所选语音模型，并请求麦克风权限。"
