.PHONY: venv install install-dev dev-backend dev-frontend lint format test clean

# ── Virtual env & dependencies ──

venv:
	uv venv
	@echo "✅ Virtual env created. Activate: source .venv/bin/activate"

install: venv
	uv sync
	@echo "✅ All dependencies installed"

install-dev: venv
	uv sync --group dev
	@echo "✅ Dev dependencies installed"

# ── Run ──

dev-backend:
	uv run uvicorn app.main:app --reload --port 8000 --app-dir backend

dev-frontend:
	cd frontend && npm install && npm run dev

# ── Quality ──

lint:
	uv run ruff check backend/
	cd frontend && npx eslint src/ 2>/dev/null || true

format:
	uv run ruff format backend/

test:
	cd backend && uv run pytest tests/ -v

# ── Cleanup ──

clean:
	rm -rf .venv/
	rm -rf frontend/node_modules/ frontend/dist/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
