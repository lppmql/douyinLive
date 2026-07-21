.PHONY: doctor start check test test-backend test-frontend lint lint-backend lint-frontend build migrate db-check docker-check

# ── 环境诊断 ──
doctor:
	./scripts/doctor.sh

# ── 启动 ──
start:
	./start.sh

# ── 完整检查（提交前必跑）──
check: test lint build db-check
	@echo "✅ 全部检查通过"

# ── 测试 ──
test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && pnpm typecheck

# ── 代码检查 ──
lint: lint-backend lint-frontend

lint-backend:
	cd backend && .venv/bin/python -m ruff check app/

lint-frontend:
	cd frontend && pnpm exec oxlint . && pnpm exec eslint .

# ── 构建 ──
build:
	cd frontend && pnpm build

# ── 数据库迁移 ──
migrate:
	cd backend && .venv/bin/alembic upgrade head

db-check:
	cd backend && .venv/bin/alembic check

# ── Docker 配置检查 ──
docker-check:
	docker compose config -q
