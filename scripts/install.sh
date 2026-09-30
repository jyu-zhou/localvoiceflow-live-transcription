#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CREATE_DESKTOP_SHORTCUT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --desktop-shortcut)
      CREATE_DESKTOP_SHORTCUT=1
      shift
      ;;
    *)
      echo "未知参数: $1"
      echo "用法: ./scripts/install.sh [--desktop-shortcut]"
      exit 1
      ;;
  esac
done

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

if ! "$PYTHON_BIN" -c 'import tkinter' >/dev/null 2>&1; then
  echo "当前 Python 缺少 tkinter。请安装带 Tk 支持的 Python 3.11/3.12 后重试。"
  exit 1
fi

echo "使用 Python $PYTHON_VERSION 创建本地环境..."
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/requirements-macos.txt"
"$ROOT_DIR/.venv/bin/python" -m pip check

mkdir -p "$HOME/Documents/MacVoiceFlow" "$HOME/Library/Caches/MacVoiceFlow/huggingface"

if [[ "$CREATE_DESKTOP_SHORTCUT" == "1" ]]; then
  desktop_dir="$HOME/Desktop"
  mkdir -p "$desktop_dir"
  shortcut_path="$desktop_dir/MacVoiceFlow.command"
  shortcut_created=1

  while [[ -e "$shortcut_path" || -L "$shortcut_path" ]]; do
    if [[ -L "$shortcut_path" && "$(readlink "$shortcut_path")" == "$ROOT_DIR/MacVoiceFlow.command" ]]; then
      shortcut_created=0
      break
    fi
    shortcut_path="$desktop_dir/MacVoiceFlow ($((++shortcut_created))).command"
  done

  if [[ "$shortcut_created" != "0" ]]; then
    ln -s "$ROOT_DIR/MacVoiceFlow.command" "$shortcut_path"
    echo "已创建桌面快捷方式: $shortcut_path"
  else
    echo "桌面快捷方式已存在: $shortcut_path"
  fi
fi

echo
echo "MacVoiceFlow 安装完成。"
echo "下一步：双击 MacVoiceFlow.command，或运行 ./scripts/run.sh"
echo "首次启动会下载所选语音模型，并请求麦克风权限。"
