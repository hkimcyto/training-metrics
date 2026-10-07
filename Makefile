.PHONY: install dev api web test lint demo build

install:
	cd backend && uv venv && uv pip install -e ".[dev]"
	cd frontend && npm ci

demo:
	cd backend && .venv/bin/python -m app.demo

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npx vitest run

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npx tsc -b && npx oxlint src && npx prettier --check src

build:
	docker build -t tri-dash .
