.PHONY: install install-ml lock migrate bootstrap verify-storage rebuild-index run test coverage lint format typecheck check

UV ?= uv

install:
	$(UV) sync --group dev --extra ml

install-ml:
	$(UV) sync --group dev --extra ml

lock:
	$(UV) lock --check

migrate:
	$(UV) run alembic upgrade head

bootstrap:
	$(UV) run --extra ml python scripts/bootstrap_existing_corpus.py

verify-storage:
	$(UV) run --extra ml python scripts/verify_storage.py

rebuild-index:
	$(UV) run --extra ml python scripts/rebuild_index.py

run:
	$(UV) run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(UV) run --extra ml pytest

coverage:
	$(UV) run --extra ml coverage run -m pytest
	$(UV) run --extra ml coverage report

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy

check: lock lint typecheck coverage
