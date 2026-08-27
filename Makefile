.PHONY: doctor start check check-diff check-docs check-backend check-frontend test test-backend test-backend-cov test-frontend test-frontend-e2e lint lint-backend lint-frontend build migrate db-check docker-check

# ── 环境诊断 ──
doctor:
	./scripts/doctor.sh

# ── 启动 ──
start:
	./start.sh

# ── 按风险选择检查，不把小改动升级成全项目验收 ──
check-diff:
	git diff --check
	git diff --cached --check

# 仅普通文档、注释、提示文案等低风险改动使用；业务知识不是普通说明文档。
check-docs: check-diff
	@echo "✅ 差异格式检查通过；请确认改动不影响业务行为"

# TESTS 必填，避免忘记选测试时意外执行全量；路径相对于 backend。
# FILES 可选，省略时 Ruff 检查 app/（静态检查很快，不调用模型或浏览器）。
check-backend: check-diff
	@test -n "$(strip $(TESTS))" || { echo '请指定相关测试，例如：make check-backend TESTS="tests/test_local_llm_client.py"'; exit 1; }
	cd backend && .venv/bin/python -m pytest -q --no-cov $(TESTS)
	cd backend && .venv/bin/python -m ruff check $(if $(strip $(FILES)),$(FILES),app/)

# 类型检查仍覆盖整个前端；Lint 可指定相关文件，不默认生产构建或启动浏览器。
# FILES 中的路径相对于 frontend。
check-frontend: check-diff test-frontend
	cd frontend && pnpm exec oxlint $(if $(strip $(FILES)),$(FILES),src/) && pnpm exec eslint $(if $(strip $(FILES)),$(FILES),src/)

# ── 高风险完整检查：保留全量测试、覆盖率、构建、迁移与 Docker 校验 ──
check: check-diff test-backend-cov test-frontend lint build db-check docker-check
	@echo "✅ 全部检查通过"

# ── 测试 ──
test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -q

# 全项目覆盖率门槛只放在明确的全量入口，局部 pytest 不再误触发全局门槛。
test-backend-cov:
	cd backend && .venv/bin/python -m pytest -q --cov=app --cov-report=term --cov-fail-under=45

test-frontend:
	cd frontend && pnpm typecheck

# 前端冒烟测试（需要后端运行在 localhost:8000 + 浏览器已安装）
# 首次运行前: cd frontend && pnpm e2e:install
test-frontend-e2e:
	cd frontend && pnpm e2e

# ── 代码检查 ──
lint: lint-backend lint-frontend

lint-backend:
	cd backend && .venv/bin/python -m ruff check app/ tests/test_check_workflow.py ../scripts/ci_change_scope.py

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
