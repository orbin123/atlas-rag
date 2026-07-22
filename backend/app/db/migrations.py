from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command


def alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_database(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
