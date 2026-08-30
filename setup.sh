#!/bin/bash
# 首次部署或依赖版本升级时运行；日常启动请使用 ./start.sh。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON_REQUIRED="3.12"
NODE_REQUIRED_MAJOR="22"
PNPM_VERSION="10.12.4"

install_brew_package() {
  local package="$1"
  if ! command -v brew >/dev/null 2>&1; then
    echo "缺少正确版本的 $package。macOS 请先安装 Homebrew，其他系统请使用系统包管理器安装。"
    exit 1
  fi
  echo "正在安装 $package..."
  brew install "$package"
}

echo "========================================"
echo "  抖音直播分析系统 — 首次环境安装"
echo "========================================"

PYTHON_BIN="$(command -v python3.12 || true)"
if [ -z "$PYTHON_BIN" ] && command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  PYTHON_BIN="$(command -v python3)"
fi
if [ -z "$PYTHON_BIN" ]; then
  install_brew_package "python@${PYTHON_REQUIRED}"
  PYTHON_BIN="$(brew --prefix "python@${PYTHON_REQUIRED}")/bin/python3.12"
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  echo "Python 版本不符合要求：必须是 ${PYTHON_REQUIRED}"
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)"
if [ "$NODE_MAJOR" != "$NODE_REQUIRED_MAJOR" ]; then
  install_brew_package "node@${NODE_REQUIRED_MAJOR}"
  export PATH="$(brew --prefix "node@${NODE_REQUIRED_MAJOR}")/bin:$PATH"
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)"
if [ "$NODE_MAJOR" != "$NODE_REQUIRED_MAJOR" ]; then
  echo "Node.js 版本不符合要求：必须是 ${NODE_REQUIRED_MAJOR}.x"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  install_brew_package ffmpeg
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "缺少 Docker。请先安装并启动 Docker Desktop：https://www.docker.com/products/docker-desktop/"
  exit 1
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "已从 .env.example 创建 .env，请先填写其中标记为“必须修改”的密码和密钥。"
fi

echo "正在安装后端 Python 依赖..."
"$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
"$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
"$BACKEND_DIR/.venv/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"
"$BACKEND_DIR/.venv/bin/python" -m playwright install chromium

echo "正在安装前端 pnpm ${PNPM_VERSION} 与依赖..."
if command -v corepack >/dev/null 2>&1; then
  PNPM_COMMAND=(corepack "pnpm@${PNPM_VERSION}")
elif command -v npm >/dev/null 2>&1; then
  npm install -g "pnpm@${PNPM_VERSION}"
  PNPM_COMMAND=(pnpm)
else
  echo "Node.js 安装不完整：找不到 corepack 或 npm"
  exit 1
fi
(cd "$FRONTEND_DIR" && "${PNPM_COMMAND[@]}" install --frozen-lockfile)

echo ""
echo "依赖安装完成。首次使用请安装并打开 Ollama：https://ollama.com/download"
echo "然后执行 ./scripts/setup_ollama_model.sh 创建项目模型。日常推荐：./start.sh standard"
echo "可选模式：lite（核心服务）/ standard（含 FunASR，推荐）"
