.PHONY: setup dev check contracts down
setup:
	python3 scripts/setup-local.py
	uv sync --directory services --frozen
	npm ci --prefix web

dev:
	python3 scripts/dev.py

check:
	uv run --directory services ruff check neuralops tests migrations
	uv run --directory services pytest -q
	npm run lint --prefix web
	npm run typecheck --prefix web
	npm run build --prefix web

contracts:
	npm run contracts --prefix web

down:
	docker compose down
