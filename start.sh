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

# 1. 启动基础 Docker 服务（ASR 默认关闭，由采集页面开关控制）
echo ""
echo "[1/5] 启动数据库 MySQL + Redis..."
cd "$ROOT_DIR"
docker compose up -d
echo "  ✅ MySQL: localhost:3306"
echo "  ✅ Redis: localhost:6379"
# 即使上次退出前开启过 ASR，新一轮启动也保持关闭，避免 8GB 电脑开机即加载模型。
pkill -f "python -m workers.asr_worker" 2>/dev/null || true
docker stop douyin_live_funasr >/dev/null 2>&1 || true
echo "  ⏸️  FunASR 默认关闭，可在数据采集页面按需开启"

# 2. 启动后端（先清理 8000 端口）
echo ""
echo "[2/5] 启动后端 FastAPI..."
clean_port 8000
cd "$BACKEND_DIR"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "  ✅ 后端: http://localhost:8000"
echo "  ✅ Swagger: http://localhost:8000/docs"

# 3. 启动采集 Worker（后台采集调度，仅在 MONITOR_ENABLED=true 时有效）
echo ""
echo "[3/5] 采集调度器由后端统一管理..."
# 兼容旧版本启动脚本留下的独立 Worker，防止两个调度器重复创建浏览器。
pkill -f "python -m workers.scraper_worker" 2>/dev/null || true
WORKER_PID=""
echo "  ✅ 避免重复启动独立 Worker 和重复创建浏览器"
echo "     设置 MONITOR_ENABLED=true 启用自动采集"

# 4. ASR Worker 默认不启动，避免 8GB 电脑启动即占用大量内存
echo ""
echo "[4/5] ASR 话术服务保持关闭..."
ASR_PID=""
echo "  ⏸️  请在数据采集页面按需开启 ASR"

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
echo "  Swagger: http://localhost:8000/docs"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，清理子进程
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $BACKEND_PID 2>/dev/null
    [ -z "$WORKER_PID" ] || kill $WORKER_PID 2>/dev/null
    kill $ASR_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait
    echo "已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持运行
wait
