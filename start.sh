#!/bin/bash
# 抖音留资直播分析系统 — 一键启动
# 用法: ./start.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "========================================"
echo "  抖音留资直播分析系统 — 启动"
echo "========================================"

# 清理旧进程：杀掉正在占用目标端口的进程
clean_port() {
  local PORT=$1
  local PIDS
  PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "  ⚠️  端口 $PORT 被占用 (PID: $(echo "$PIDS" | tr '\n' ' '))，正在释放..."
    kill $PIDS 2>/dev/null || true
    sleep 1
    # 如果没杀死，强制杀
    PIDS=$(lsof -ti ":$PORT" 2>/dev/null || true)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
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
  local ATTEMPTS=240
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
  echo "  ❌ DataEase 240 秒内未通过健康检查，最近日志如下："
  docker logs --tail 30 douyin_live_dataease 2>&1 || true
  return 1
}

# 1. 启动基础 Docker 服务与 DataEase（ASR 由后端按安全资源限制自动启动）
echo ""
echo "[1/5] 启动 MySQL、Redis 与 DataEase..."
cd "$ROOT_DIR"
docker compose --profile dataease up -d mysql redis dataease
echo "  ✅ MySQL: localhost:3306"
echo "  ✅ Redis: localhost:6379"
echo "  ⏳ DataEase 正在启动，首次初始化可能需要约 3 分钟"
echo "  ℹ️  FunASR 将由后端自动启动：单任务并发、队列上限 5"

# 2. 启动后端（先清理 8000 端口）
echo ""
echo "[2/5] 启动后端 FastAPI..."
clean_port 8000
cd "$BACKEND_DIR"
source .venv/bin/activate
alembic upgrade head
echo "  ✅ 数据库迁移已更新到最新版本"
python -m scripts.configure_dataease_reader
echo "  ✅ DataEase 专用只读账号已配置"
if [ "${BACKEND_RELOAD:-false}" = "true" ]; then
  uvicorn app.main:app --reload --port 8000 &
  echo "  ℹ️  已开启后端开发热更新"
else
  uvicorn app.main:app --port 8000 &
  echo "  ℹ️  后端使用稳定单进程模式；开发时可设置 BACKEND_RELOAD=true"
fi
BACKEND_PID=$!
if ! wait_for_backend; then
  exit 1
fi
echo "  ✅ 后端: http://localhost:8000"
echo "  ✅ Swagger: http://localhost:8000/docs"
if ! wait_for_dataease; then
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi
echo "  ✅ DataEase: http://localhost:8100"

# 3. 启动采集 Worker（后台采集调度，仅在 MONITOR_ENABLED=true 时有效）
echo ""
echo "[3/5] 采集调度器由后端统一管理..."
# 兼容旧版本启动脚本留下的独立 Worker，防止两个调度器重复创建浏览器。
pkill -f "python -m workers.scraper_worker" 2>/dev/null || true
WORKER_PID=""
echo "  ✅ 避免重复启动独立 Worker 和重复创建浏览器"
echo "     设置 MONITOR_ENABLED=true 启用自动采集"

# 4. ASR 由后端统一启动，避免重复 Worker
echo ""
echo "[4/5] ASR 话术服务由后端统一管理..."
ASR_PID=""
echo "  ✅ 默认开启，限制 2 核 / 1.8GB / 单任务并发，可在采集页面关闭"

# 5. 启动前端（先清理 9527 端口）
echo ""
echo "[5/5] 启动前端..."
clean_port 9527
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!
echo "  ✅ 前端: http://localhost:9527"

echo ""
echo "========================================"
echo "  启动完成！"
echo "  前端: http://localhost:9527"
echo "  后端: http://localhost:8000"
echo "  DataEase: http://localhost:8100"
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
