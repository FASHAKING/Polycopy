.PHONY: install test lint run-api run-bot run-worker web up down fmt start

# One command: setup (first run) + api + bot + worker + web
start:
	bash scripts/start.sh

install:
	cd backend && pip install -e ".[dev]"
	cd web && npm install

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check src/ tests/

fmt:
	cd backend && ruff check --fix src/ tests/

run-api:
	cd backend && polycopy-api

run-bot:
	cd backend && polycopy-bot

run-worker:
	cd backend && polycopy-worker

web:
	cd web && npm run dev

up:
	docker compose up --build

down:
	docker compose down
