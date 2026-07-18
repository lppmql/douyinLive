.PHONY: doctor start test test-backend test-frontend lint build migrate

doctor:
	./scripts/doctor.sh

start:
	./start.sh

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && pnpm typecheck

lint:
	cd frontend && pnpm exec oxlint . && pnpm exec eslint .

build:
	cd frontend && pnpm build

migrate:
	cd backend && .venv/bin/alembic upgrade head
