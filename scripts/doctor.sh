#!/bin/bash

set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FAILURES=0
WARNINGS=0

pass() { printf "[通过] %s\n" "$1"; }
warn() { printf "[提醒] %s\n" "$1"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf "[失败] %s\n" "$1"; FAILURES=$((FAILURES + 1)); }

has_command() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "$1 已安装"
  else
    fail "$1 未安装"
  fi
}

env_value() {
  sed -n "s/^$1=//p" "$ROOT_DIR/.env" 2>/dev/null | tail -n 1
}

printf "零食店避坑直播运营复盘系统 - 环境自检\n\n"

for command_name in docker python3 node pnpm ffmpeg curl; do
  has_command "$command_name"
done

if [ -f "$ROOT_DIR/.env" ]; then
  pass ".env 已存在"
  DB_USER_VALUE="$(env_value DB_USER)"
  DB_PASSWORD_VALUE="$(env_value DB_PASSWORD)"
  JWT_VALUE="$(env_value JWT_SECRET_KEY)"
  REDIS_VALUE="$(env_value REDIS_URL)"
  DEBUG_VALUE="$(env_value DEBUG)"
  if [ -z "$DB_PASSWORD_VALUE" ] || [ "$DB_PASSWORD_VALUE" = "root123" ] || [ ${#DB_PASSWORD_VALUE} -lt 16 ]; then
    warn "DB_PASSWORD 为空或仍为弱密码，请改为至少 16 位随机字符串"
  fi
  if [ "$DB_USER_VALUE" = "root" ]; then
    warn "业务后端仍使用 MySQL root；正式部署应迁移到独立业务账号"
  fi
  if [ ${#JWT_VALUE} -lt 32 ] || [ "$JWT_VALUE" = "replace-with-a-long-random-secret" ]; then
    warn "JWT_SECRET_KEY 少于 32 位或仍为占位值"
  fi
  if [[ "$REDIS_VALUE" != *"@"* ]]; then
    warn "Redis 尚未启用密码；当前仅适合本机单用户环境"
  fi
  if [ "$DEBUG_VALUE" = "true" ]; then
    warn "DEBUG=true，仅建议本地开发使用"
  fi
else
  fail ".env 不存在，请先执行 cp .env.example .env 并修改密码"
fi

if [ -x "$ROOT_DIR/backend/.venv/bin/python" ]; then
  pass "后端 Python 虚拟环境可用"
  if "$ROOT_DIR/backend/.venv/bin/python" -c "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).exists(); p.stop(); raise SystemExit(0 if ok else 1)" >/dev/null 2>&1; then
    pass "Playwright Chromium 已安装"
  else
    fail "Playwright Chromium 缺失，请在 backend 中执行 playwright install chromium"
  fi
else
  fail "backend/.venv 不可用"
fi

if docker info >/dev/null 2>&1; then
  pass "Docker 服务可用"
  if (cd "$ROOT_DIR" && docker compose config >/dev/null 2>&1); then
    pass "docker-compose.yml 配置有效"
  else
    fail "docker-compose.yml 配置无效，请检查 .env"
  fi
  for service in mysql redis dataease prometheus grafana; do
    if [ "$(cd "$ROOT_DIR" && docker compose --profile dataease --profile observability ps --status running --services 2>/dev/null | grep -c "^${service}$")" -gt 0 ]; then
      pass "$service 容器运行中"
    else
      warn "$service 容器未运行"
    fi
  done
else
  fail "Docker Desktop 未运行"
fi

if curl -fsS --max-time 5 http://127.0.0.1:8100/ >/dev/null 2>&1; then
  pass "DataEase 页面可访问"
  if "$ROOT_DIR/backend/.venv/bin/python" "$ROOT_DIR/backend/scripts/check_dataease_crypto.py" >/dev/null 2>&1; then
    pass "DataEase 登录 RSA 公钥链路正常"
  else
    fail "DataEase 登录 RSA 公钥链路异常"
  fi
else
  warn "DataEase 页面不可访问；尚未启动项目时可忽略"
fi

if curl -fsS --max-time 3 http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
  pass "Prometheus 已就绪"
else
  warn "Prometheus 未就绪；执行 ./start.sh 后应自动启动"
fi

if curl -fsS --max-time 3 http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
  pass "Grafana 已就绪"
else
  warn "Grafana 未就绪；执行 ./start.sh 后应自动启动"
fi

if tail -n 500 "$ROOT_DIR/data/dataease/logs/dataease/error.log" 2>/dev/null | grep -q "BadPaddingException"; then
  warn "DataEase 近期出现旧 RSA 公钥解密失败；请清除 localhost:8100 的 DataEaseKey 站点缓存后刷新登录页"
fi

if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  pass "后端健康接口可访问"
else
  warn "后端健康接口不可访问；尚未启动项目时可忽略"
fi

AVAILABLE_GB=$(df -Pk "$ROOT_DIR" | awk 'NR==2 {printf "%d", $4/1024/1024}')
if [ "$AVAILABLE_GB" -lt 10 ]; then
  warn "磁盘剩余 ${AVAILABLE_GB}GB，建议至少保留 10GB 给回放缓存和模型"
else
  pass "磁盘剩余 ${AVAILABLE_GB}GB"
fi

printf "\n自检完成：失败 %d 项，提醒 %d 项。\n" "$FAILURES" "$WARNINGS"
if [ "$FAILURES" -gt 0 ]; then
  exit 1
fi
