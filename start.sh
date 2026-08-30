#!/bin/bash
# 抖音留资直播分析系统 — 一键启动
# 用法: ./start.sh [lite|standard]

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
START_LOCK_DIR="$ROOT_DIR/.runtime/start.lock"
RUN_MODE="${1:-standard}"
case "$RUN_MODE" in
  lite|standard) ;;
  *) echo "启动模式只能是 lite 或 standard"; exit 1 ;;
esac

env_value() {
  local KEY="$1"
  sed -n "s/^${KEY}=//p" "$ROOT_DIR/.env" 2>/dev/null | tail -n 1
}

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
  # 启动中途失败时，也只停止本次脚本创建的 Ollama；绝不碰用户已有服务。
  if [ -n "${OLLAMA_PID:-}" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
    wait "$OLLAMA_PID" 2>/dev/null || true
  fi
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
echo "  模式: $RUN_MODE"
echo "========================================"

# 0. 快速环境自检。首次安装与大体积下载统一由 setup.sh 负责。
echo ""
echo "  🔍 环境快速自检..."
for REQUIRED in node ffmpeg docker curl ollama; do
  if ! command -v "$REQUIRED" >/dev/null 2>&1; then
    echo "  ❌ 缺少 $REQUIRED，请先运行 ./setup.sh"
    exit 1
  fi
done
if [ ! -x "$BACKEND_DIR/.venv/bin/python" ] || [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]; then
  echo "  ❌ 项目依赖尚未安装完整，请先运行 ./setup.sh"
  exit 1
fi
if ! "$BACKEND_DIR/.venv/bin/python" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  echo "  ❌ 后端虚拟环境不是 Python 3.12，请重新运行 ./setup.sh"
  exit 1
fi
if [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)" != "22" ]; then
  echo "  ❌ Node.js 必须是 22.x，请重新运行 ./setup.sh"
  exit 1
fi
if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "  ❌ 未找到 .env，请先运行 ./setup.sh 并填写配置"
  exit 1
fi
if [ "$(env_value DB_USER)" = "root" ]; then
  echo "  ❌ 旧配置仍使用 DB_USER=root，请按 .env.example 改为 douyin_app，并设置 MYSQL_ROOT_PASSWORD"
  exit 1
fi
# Docker Desktop 是 GUI 应用，不能自动装，只能提示
if ! docker info >/dev/null 2>&1; then
  echo "  ❌ Docker 未安装或未启动"
  echo "  请先下载 Docker Desktop：https://www.docker.com/products/docker-desktop/"
  echo "  安装并启动后重新运行 ./start.sh"
  exit 1
fi
echo "  ✅ Docker 已运行"

# 本地 AI 不依赖云端密钥。若 Ollama 应用尚未启动，则由本次编排器启动服务；
# 已由用户或 Ollama 应用管理的服务只做复用，退出项目时不会误停。
OLLAMA_PID=""
OLLAMA_SERVICE_URL="$(cd "$BACKEND_DIR" && .venv/bin/python -m scripts.check_local_ai --service-url)"
if ! curl --noproxy '*' -fsS --max-time 3 "$OLLAMA_SERVICE_URL/api/tags" >/dev/null 2>&1; then
  echo "  ⏳ 正在启动本地 Ollama 服务..."
  OLLAMA_HOST="${OLLAMA_SERVICE_URL#http://}" OLLAMA_NO_CLOUD=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 \
    start_in_own_session "$(command -v ollama)" serve
  OLLAMA_PID=$DETACHED_PID
  for ((i = 1; i <= 30; i++)); do
    if curl --noproxy '*' -fsS --max-time 2 "$OLLAMA_SERVICE_URL/api/tags" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
      echo "  ❌ Ollama 服务启动失败，请打开 Ollama 应用后重试"
      exit 1
    fi
    sleep 1
  done
fi
if ! curl --noproxy '*' -fsS --max-time 3 "$OLLAMA_SERVICE_URL/api/tags" >/dev/null 2>&1; then
  echo "  ❌ Ollama 服务 30 秒内未就绪"
  exit 1
fi
OLLAMA_MODEL_VALUE="$(env_value OLLAMA_MODEL)"
OLLAMA_MODEL_VALUE="${OLLAMA_MODEL_VALUE:-douyin-live-qwen}"
if ! (cd "$BACKEND_DIR" && .venv/bin/python -m scripts.check_local_ai); then
  echo "  ❌ 缺少本地模型 $OLLAMA_MODEL_VALUE"
  echo "     首次使用请执行：./scripts/setup_ollama_model.sh"
  exit 1
fi
echo "  ✅ 本地 Ollama 模型已就绪：$OLLAMA_MODEL_VALUE"

echo "  🎉 环境自检通过"

# 清理旧进程：先给后端和前端足够时间安全退出，再在确实卡死时强制结束。
clean_port() {
  local PORT=$1
  local PIDS
  local PID
  local PROCESS_NAME
  local WAITED=0
  PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    # macOS 上 Docker Desktop 负责容器端口转发，绝不能按端口直接杀掉。
    for PID in $PIDS; do
      PROCESS_NAME=$(ps -p "$PID" -o command= 2>/dev/null || true)
      case "$PROCESS_NAME" in
        *Docker*|*docker*|*com.docker*)
          echo "  ❌ 端口 $PORT 由 Docker 服务占用，已拒绝结束 Docker Desktop"
          echo "     请先检查占用该端口的容器：docker ps --filter publish=$PORT"
          return 1
          ;;
      esac
    done
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
    if [ -n "$HEALTH_RESPONSE" ] && "$BACKEND_DIR/.venv/bin/python" -c 'import json, sys; sys.exit(json.load(sys.stdin).get("status") != "ok")' <<< "$HEALTH_RESPONSE"; then
      return 0
    fi
    sleep 1
  done
  echo "  ❌ 后端 60 秒内未通过健康检查，请检查 MySQL、Redis 和后端日志"
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
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

# 1. 启动基础 Docker 服务（ASR 由后端按安全资源限制自动启动）
echo ""
echo "[1/6] 启动 MySQL、Redis 与 Qdrant..."
cd "$ROOT_DIR"
docker compose up -d mysql redis qdrant
echo "  ✅ MySQL: localhost:3306"
echo "  ✅ Redis: localhost:6379"
# 已有 MySQL 数据卷不会再次执行镜像的 MYSQL_USER 初始化，因此每次启动都用
# 管理凭据幂等校准一次受限业务账号。后续 FastAPI 不使用 root。
MYSQL_ROOT_PASSWORD_VALUE="$(env_value MYSQL_ROOT_PASSWORD)"
MYSQL_ROOT_PASSWORD_VALUE="${MYSQL_ROOT_PASSWORD_VALUE:-$(env_value DB_PASSWORD)}"
MYSQL_READY=false
for ((i = 1; i <= 60; i++)); do
  if docker exec -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD_VALUE" douyin_live_mysql \
    mysqladmin ping -h 127.0.0.1 -uroot --silent >/dev/null 2>&1; then
    MYSQL_READY=true
    break
  fi
  sleep 1
done
if [ "$MYSQL_READY" != "true" ]; then
  echo "  ❌ MySQL 60 秒内未就绪或 MYSQL_ROOT_PASSWORD 不正确"
  exit 1
fi
cd "$BACKEND_DIR"
"$BACKEND_DIR/.venv/bin/python" -m scripts.configure_database_users
echo "  ✅ MySQL 业务账号权限已校准"
if ! wait_for_http "Qdrant" "http://127.0.0.1:6333/healthz" "douyin_live_qdrant" 60; then
  exit 1
fi
echo "  ✅ Qdrant: http://localhost:6333"
echo "  ℹ️  FunASR 将在第 5 步启动；ASR Worker 由后端按页面开关管理"
# 2. 预留启动阶段编号，保持日志与故障定位步骤稳定。
echo ""
echo "[2/6] 基础服务已就绪，准备启动应用..."

# 3. 启动后端（先清理 8000 端口）
echo ""
echo "[3/6] 启动后端 FastAPI..."
clean_port 8000
cd "$BACKEND_DIR"
source .venv/bin/activate
alembic upgrade head
echo "  ✅ 数据库迁移已更新到最新版本"
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
if [ "$RUN_MODE" = "lite" ] || [ "$(env_value ASR_AUTO_START)" != "true" ]; then
  echo "  ℹ️  ASR_AUTO_START=false，已跳过可选的 FunASR"
  FUNASR_READY=false
  ASR_PID=""
else
docker compose --profile funasr up -d funasr
echo "  ⏳ FunASR 容器启动中，首次下载或崩溃恢复可能需要 5-15 分钟..."

# 等待 FunASR 端口就绪（WebSocket 服务，用 Python 检测 TCP 连通性）
FUNASR_READY=false
FUNASR_WAIT_SECONDS="$(env_value ASR_ENGINE_READY_TIMEOUT_SECONDS)"
if ! [[ "$FUNASR_WAIT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  FUNASR_WAIT_SECONDS=30
fi
if [ "$FUNASR_WAIT_SECONDS" -gt 30 ]; then
  FUNASR_WAIT_SECONDS=30
fi
for ((i = 1; i <= FUNASR_WAIT_SECONDS; i++)); do
  # 先确认容器在运行
  if [ "$(docker inspect -f '{{.State.Running}}' douyin_live_funasr 2>/dev/null)" != "true" ]; then
    echo "  ⚠️  FunASR 容器异常退出，主系统将继续启动；最近日志如下："
    docker logs --tail 30 douyin_live_funasr 2>&1 || true
    break
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
  echo "  ⚠️  FunASR 在 ${FUNASR_WAIT_SECONDS} 秒内未就绪，将在后台继续加载；最近日志如下："
  docker logs --tail 30 douyin_live_funasr 2>&1 || true
  echo "  ℹ️  语音转写暂不可用；可稍后重启 FunASR 或设置 ASR_AUTO_START=false"
else
  echo "  ✅ FunASR: ws://localhost:10096"
  echo "  ℹ️  ASR Worker 由后端按页面开关管理，并根据电脑资源实时调节并发"
fi
ASR_PID=""
fi

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
    [ -z "$OLLAMA_PID" ] || kill "$OLLAMA_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持运行
wait
