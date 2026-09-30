#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
"$ROOT_DIR/scripts/install.sh" --desktop-shortcut

echo
read -r -n 1 -s -p "按任意键关闭窗口..."
echo
