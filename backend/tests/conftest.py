from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'atlas.db'}",
        storage_root=tmp_path / "storage",
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
