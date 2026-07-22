from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from alembic import command
from app.db.migrations import alembic_config, upgrade_database
from app.db.session import create_database_engine

EXPECTED_TABLES = {
    "alembic_version",
    "chunks",
    "document_pages",
    "documents",
    "evaluation_results",
    "evaluation_runs",
    "index_state",
    "ingestion_jobs",
    "queries",
    "query_sources",
}


@pytest.mark.integration
def test_upgrade_empty_database_and_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
            assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20260721_0003"
            )
    finally:
        engine.dispose()

    config = alembic_config(database_url)
    command.downgrade(config, "base")
    downgrade_engine = create_database_engine(database_url)
    try:
        assert inspect(downgrade_engine).get_table_names() == ["alembic_version"]
    finally:
        downgrade_engine.dispose()
    command.upgrade(config, "head")
