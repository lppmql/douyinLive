#!/bin/bash
# 抖音留资直播分析系统 — 一键启动
# 用法: ./start.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
START_LOCK_DIR="$ROOT_DIR/.runtime/start.lock"

# 同一项目只能运行一个一键启动编排器。重复启动会先杀掉旧后端，可能在
# 采集过程中关闭 BrowserContext；使用原子目录锁可以在碰业务进程前直接拦住。
acquire_start_lock() {
  mkdir -p "$ROOT_DIR/.runtime"
  if mkdir "$START_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$START_LOCK_DIR/pid"
    return 0
  fi

  local EXISTING_PID=""
  EXISTING_PID=$(cat "$START_LOCK_DIR/pid" 2>/dev/null || true)
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "已有一键启动任务正在运行（PID: $EXISTING_PID），本次不重复启动。"
    echo "如需重启，请先在原启动终端按 Ctrl+C，等待采集任务安全停止后再执行。"
    exit 1
  fi

  # 上次异常退出可能留下空锁；只清理本项目固定目录中的单个 PID 文件。
  find "$START_LOCK_DIR" -maxdepth 1 -type f -name pid -delete 2>/dev/null || true
  rmdir "$START_LOCK_DIR" 2>/dev/null || true
  if ! mkdir "$START_LOCK_DIR" 2>/dev/null; then
    echo "无法取得启动锁，请检查 $START_LOCK_DIR"
    exit 1
  fi
  printf '%s\n' "$$" > "$START_LOCK_DIR/pid"
}

release_start_lock() {
  find "$START_LOCK_DIR" -maxdepth 1 -type f -name pid -delete 2>/dev/null || true
  rmdir "$START_LOCK_DIR" 2>/dev/null || true
}

# 后端、前端各自使用独立进程组。这样终端 Ctrl+C 只通知本脚本，
# 再由 cleanup 按“调度器 → 浏览器 → 前端”的顺序发送 SIGTERM。
start_in_own_session() {
  "$BACKEND_DIR/.venv/bin/python" -c \
    'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
    "$@" &
  DETACHED_PID=$!
}

acquire_start_lock
trap release_start_lock EXIT

echo "========================================"
echo "  抖音留资直播分析系统 — 启动"
echo "========================================"

# 0. 环境自检 + 自动安装（macOS）
echo ""
echo "  🔍 环境自检与自动安装..."

# brew 是 macOS 包管理器，后续自动安装都靠它
if ! command -v brew >/dev/null 2>&1; then
  echo "  ❌ 未找到 Homebrew（macOS 包管理器）"
  echo "  请先安装：/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
  echo "  安装完成后重新运行 ./start.sh"
  exit 1
fi
echo "  ✅ Homebrew"

# 逐个检查必要工具，缺了就自动装
auto_install() {
  local NAME="$1"
  local BIN="$2"
  local BREW_PKG="$3"
  if command -v "$BIN" >/dev/null 2>&1; then
    echo "  ✅ $NAME（$(command -v "$BIN")）"
    return 0
  fi
  echo "  ⏳ $NAME 未安装，正在用 Homebrew 自动安装..."
  if brew install "$BREW_PKG" 2>&1 | tail -1; then
    echo "  ✅ $NAME 安装完成"
  else
    echo "  ❌ $NAME 自动安装失败，请手动执行：brew install $BREW_PKG"
    exit 1
  fi
}

auto_install "Python 3" python3 python@3.12
auto_install "Node.js" node node@22
auto_install "FFmpeg" ffmpeg ffmpeg

# pnpm 通过 npm 安装（node 此时一定可用了）
if ! command -v pnpm >/dev/null 2>&1; then
  echo "  ⏳ pnpm 未安装，正在通过 npm 全局安装..."
  npm install -g pnpm 2>&1 | tail -1 && echo "  ✅ pnpm 安装完成" || { echo "  ❌ pnpm 安装失败"; exit 1; }
else
  echo "  ✅ pnpm（$(command -v pnpm)）"
fi

# Docker Desktop 是 GUI 应用，不能自动装，只能提示
if ! docker info >/dev/null 2>&1; then
  echo "  ❌ Docker 未安装或未启动"
  echo "  请先下载 Docker Desktop：https://www.docker.com/products/docker-desktop/"
  echo "  安装并启动后重新运行 ./start.sh"
  exit 1
fi
echo "  ✅ Docker 已运行"

echo "  🎉 环境自检通过"

# 清理旧进程：先给后端和前端足够时间安全退出，再在确实卡死时强制结束。
clean_port() {
  local PORT=$1
  local PIDS
  local WAITED=0
  PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "  ⚠️  端口 $PORT 被占用 (PID: $(echo "$PIDS" | tr '\n' ' '))，正在释放..."
    kill $PIDS 2>/dev/null || true
    while [ "$WAITED" -lt 60 ]; do
      PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
      [ -z "$PIDS" ] && break
      sleep 1
      WAITED=$((WAITED + 1))
    done
    PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
      echo "  ⚠️  等待 60 秒后进程仍未退出，执行最终强制清理"
      kill -9 $PIDS 2>/dev/null || true
    fi
    echo "  ✅ 端口 $PORT 已释放"
  fi
}

wait_for_backend() {
  local ATTEMPTS=60
  local HEALTH_RESPONSE
  for ((i = 1; i <= ATTEMPTS; i++)); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "  ❌ 后端进程已退出，请根据上方 FastAPI 错误修正配置后重试"
      wait "$BACKEND_PID" 2>/dev/null || true
      return 1
    fi
    HEALTH_RESPONSE=$(curl -fsS --max-time 2 http://127.0.0.1:8000/health 2>/dev/null || true)
    if [ -n "$HEALTH_RESPONSE" ] && python -c 'import json, sys; sys.exit(json.load(sys.stdin).get("status") != "ok")' <<< "$HEALTH_RESPONSE"; then
      return 0
    fi
    sleep 1
  done
  echo "  ❌ 后端 60 秒内未通过健康检查，请检查 MySQL、Redis 和后端日志"
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
  return 1
}

wait_for_dataease() {
  local ATTEMPTS=600
  local RUNNING
  local HEALTH
  for ((i = 1; i <= ATTEMPTS; i++)); do
    RUNNING=$(docker inspect -f '{{.State.Running}}' douyin_live_dataease 2>/dev/null || true)
    HEALTH=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' douyin_live_dataease 2>/dev/null || true)
    if [ "$HEALTH" = "healthy" ]; then
      return 0
    fi
    if [ "$RUNNING" != "true" ]; then
      echo "  ❌ DataEase 容器已退出，最近日志如下："
      docker logs --tail 30 douyin_live_dataease 2>&1 || true
      return 1
    fi
    sleep 1
  done
  echo "  ❌ DataEase 600 秒内未通过健康检查，最近日志如下："
  docker logs --tail 30 douyin_live_dataease 2>&1 || true
  return 1
}

wait_for_http() {
  local NAME=$1
  local URL=$2
  local CONTAINER=$3
  local ATTEMPTS=${4:-60}
  local RUNNING
  for ((i = 1; i <= ATTEMPTS; i++)); do
    if curl -fsS --max-time 2 "$URL" >/dev/null 2>&1; then
      return 0
    fi
    RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)
    if [ "$RUNNING" != "true" ]; then
      echo "  ❌ $NAME 容器已退出，最近日志如下："
      docker logs --tail 30 "$CONTAINER" 2>&1 || true
      return 1
    fi
    sleep 1
  done
  echo "  ❌ $NAME 未在 ${ATTEMPTS} 秒内通过健康检查，最近日志如下："
  docker logs --tail 30 "$CONTAINER" 2>&1 || true
  return 1
}

# 1. 启动基础 Docker 服务与 DataEase（ASR 由后端按安全资源限制自动启动）
echo ""
echo "[1/6] 启动 MySQL、Redis、Qdrant 与 DataEase..."
cd "$ROOT_DIR"
docker compose --profile dataease up -d mysql redis qdrant dataease
echo "  ✅ MySQL: localhost:3306"
echo "  ✅ Redis: localhost:6379"
if ! wait_for_http "Qdrant" "http://127.0.0.1:6333/healthz" "douyin_live_qdrant" 60; then
  exit 1
fi
echo "  ✅ Qdrant: http://localhost:6333"
echo "  ⏳ DataEase 正在启动，8GB 电脑首次初始化可能需要 3-10 分钟"
echo "  ℹ️  FunASR 将在第 5 步启动；ASR Worker 由后端按页面开关管理"
if ! wait_for_dataease; then
  exit 1
fi
if ! "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/scripts/check_dataease_crypto.py" --timeout 60; then
  echo "  ❌ DataEase 公钥链路异常，请先检查 core_rsa 数据和 DataEase 日志"
  exit 1
fi
if ! curl -fsS --max-time 60 http://127.0.0.1:8100/ | grep -q "douyinLive.dataeaseKeySha256"; then
  echo "  ❌ DataEase 登录密钥自动刷新层未生效，请重新创建 dataease 容器"
  exit 1
fi
echo "  ✅ DataEase 登录密钥自动刷新层已启用"
echo "  ✅ DataEase: http://localhost:8100"

# 2. ASR 尚未启动时先准备监控组件，避免首次拉镜像与模型争抢内存。
echo ""
echo "[2/6] 启动 Prometheus 与 Grafana..."
cd "$ROOT_DIR"
docker compose --profile observability up -d prometheus grafana
if ! wait_for_http "Prometheus" "http://127.0.0.1:9090/-/ready" "douyin_live_prometheus" 90; then
  exit 1
fi
if ! wait_for_http "Grafana" "http://127.0.0.1:3000/api/health" "douyin_live_grafana" 90; then
  exit 1
fi
echo "  ✅ Prometheus: http://localhost:9090"
echo "  ✅ Grafana: http://localhost:3000"

# 3. 启动后端（先清理 8000 端口）
echo ""
echo "[3/6] 启动后端 FastAPI..."
clean_port 8000
cd "$BACKEND_DIR"
source .venv/bin/activate
alembic upgrade head
echo "  ✅ 数据库迁移已更新到最新版本"
python -m scripts.configure_dataease_reader
echo "  ✅ DataEase 专用只读账号已配置"
if [ "${BACKEND_RELOAD:-false}" = "true" ]; then
  start_in_own_session "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --reload --port 8000
  echo "  ℹ️  已开启后端开发热更新"
else
  start_in_own_session "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --port 8000
  echo "  ℹ️  后端使用稳定单进程模式；开发时可设置 BACKEND_RELOAD=true"
fi
BACKEND_PID=$DETACHED_PID
if ! wait_for_backend; then
  exit 1
fi
echo "  ✅ 后端: http://localhost:8000"
echo "  ✅ Swagger: http://localhost:8000/docs"

# 4. 启动采集 Worker（后台采集调度，仅在 MONITOR_ENABLED=true 时有效）
echo ""
echo "[4/6] 采集调度器由后端统一管理..."
# 兼容旧版本启动脚本留下的独立 Worker，防止两个调度器重复创建浏览器。
pkill -f "python -m workers.scraper_worker" 2>/dev/null || true
WORKER_PID=""
echo "  ✅ 避免重复启动独立 Worker 和重复创建浏览器"
echo "     设置 MONITOR_ENABLED=true 启用自动采集"

# 5. 启动 FunASR 语音转写容器
echo ""
echo "[5/6] 启动 FunASR 语音转写服务..."
cd "$ROOT_DIR"
docker compose --profile funasr up -d funasr
echo "  ⏳ FunASR 容器启动中，首次需下载模型（约 1-3 分钟，8GB Mac 请耐心等待）..."

# 等待 FunASR 端口就绪（WebSocket 服务，用 Python 检测 TCP 连通性）
FUNASR_READY=false
for ((i = 1; i <= 300; i++)); do
  # 先确认容器在运行
  if [ "$(docker inspect -f '{{.State.Running}}' douyin_live_funasr 2>/dev/null)" != "true" ]; then
    echo "  ❌ FunASR 容器异常退出，最近日志如下："
    docker logs --tail 30 douyin_live_funasr 2>&1 || true
    exit 1
  fi
  # 用 Python 检测 WebSocket 端口是否已监听
  if "$BACKEND_DIR/.venv/bin/python" -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('127.0.0.1', 10096))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    FUNASR_READY=true
    break
  fi
  sleep 1
done

if [ "$FUNASR_READY" != "true" ]; then
  echo "  ❌ FunASR 在 300 秒内未就绪，最近日志如下："
  docker logs --tail 30 douyin_live_funasr 2>&1 || true
  exit 1
fi
echo "  ✅ FunASR: ws://localhost:10096"
echo "  ℹ️  ASR Worker 由后端按页面开关管理，并根据电脑资源实时调节并发"
ASR_PID=""

# 6. 启动前端（先清理 9527 端口）
echo ""
echo "[6/6] 启动前端..."
clean_port 9527
cd "$FRONTEND_DIR"
# 直接记录 Vite 进程 PID，避免只停止 pnpm 外壳后留下占用 9527 的子进程。
start_in_own_session "$FRONTEND_DIR/node_modules/.bin/vite" --mode test
FRONTEND_PID=$DETACHED_PID
echo "  ✅ 前端: http://localhost:9527"

echo ""
echo "========================================"
echo "  启动完成！"
echo "  前端: http://localhost:9527"
echo "  后端: http://localhost:8000"
echo "  DataEase: http://localhost:8100"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana: http://localhost:3000"
echo "  Swagger: http://localhost:8000/docs"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，清理子进程
cleanup() {
    echo ""
    echo "正在停止服务..."
    cd "$BACKEND_DIR"
    .venv/bin/python -c "from app.services.asr.control import stop_asr_runtime; stop_asr_runtime()" 2>/dev/null || true
    [ -z "$BACKEND_PID" ] || kill "$BACKEND_PID" 2>/dev/null || true
    [ -z "$WORKER_PID" ] || kill "$WORKER_PID" 2>/dev/null || true
    [ -z "$ASR_PID" ] || kill "$ASR_PID" 2>/dev/null || true
    [ -z "$FRONTEND_PID" ] || kill "$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持运行
wait
