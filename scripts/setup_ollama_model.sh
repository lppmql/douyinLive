#!/bin/bash
# 下载官方模型并创建项目专用的 64K 上下文模型。
# 这是首次安装或模型被删除后的手动初始化脚本，不会在日常启动时重复下载。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_MODEL="qwen3.5:9b"
PROJECT_MODEL="douyin-live-qwen"
OLLAMA_URL="http://127.0.0.1:11434"
# 只对默认本机服务安装模型，忽略终端中可能残留的远程 Ollama 地址。
export OLLAMA_HOST=127.0.0.1:11434

if ! command -v ollama >/dev/null 2>&1; then
  echo "❌ 未安装 Ollama，请先从 https://ollama.com/download 安装。"
  exit 1
fi

if ! curl --noproxy '*' -fsS --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "❌ Ollama 服务未运行。请先打开 Ollama 应用，再重新执行本脚本。"
  exit 1
fi

echo "[1/2] 下载或校验官方模型 $BASE_MODEL ..."
ollama pull "$BASE_MODEL"

echo "[2/2] 创建项目专用模型 $PROJECT_MODEL（64K 上下文）..."
ollama create "$PROJECT_MODEL" -f "$ROOT_DIR/deploy/ollama/Modelfile"

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Eq "^${PROJECT_MODEL}(:latest)?$"; then
  echo "❌ 项目模型创建后未出现在 Ollama 列表中。"
  exit 1
fi

echo "✅ 本地模型已就绪：$PROJECT_MODEL"
