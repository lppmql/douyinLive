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

# 1. 启动 Docker 服务
echo ""
echo "[1/3] 启动数据库 MySQL + Redis..."
cd "$ROOT_DIR"
docker compose up -d mysql redis 2>/dev/null || docker compose up -d
echo "  ✅ MySQL: localhost:3306"
echo "  ✅ Redis: localhost:6379"

# 2. 启动后端
echo ""
echo "[2/3] 启动后端 FastAPI..."
cd "$BACKEND_DIR"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "  ✅ 后端: http://localhost:8000"
echo "  ✅ Swagger: http://localhost:8000/docs"

# 3. 启动前端
echo ""
echo "[3/3] 启动前端..."
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!
echo "  ✅ 前端: http://localhost:5173"

echo ""
echo "========================================"
echo "  启动完成！"
echo "  前端: http://localhost:5173"
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
    kill $FRONTEND_PID 2>/dev/null
    wait
    echo "已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持运行
wait
