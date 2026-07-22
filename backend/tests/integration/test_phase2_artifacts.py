from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.artifacts import read_artifact_bundle


@pytest.mark.integration
def test_real_phase2_artifacts_validate_against_selected_policy(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'artifacts.db'}",
        storage_root=tmp_path / "storage",
    )

    bundle = read_artifact_bundle(
        repository_root,
        settings,
        validate_legacy_vectors=False,
    )

    assert len(bundle.documents) == 60
    assert len(bundle.pages) == 1848
    assert bundle.legacy_chunk_count == 2729
    assert bundle.legacy_dimension == 384
    assert bundle.selected_chunk_count == 7336
    assert len(bundle.gold_questions) == 33
    assert len(bundle.evaluation_results) == 33
    assert all(len(checksum) == 64 for checksum in bundle.checksums.values())
