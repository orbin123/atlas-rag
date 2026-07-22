from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_EMBEDDING_REVISION, Settings


def test_defaults_bind_phase_zero_policy(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, storage_root=tmp_path)

    assert settings.embedding_revision == DEFAULT_EMBEDDING_REVISION
    assert settings.embedding_max_input_tokens == 256
    assert settings.embedding_dimension == 384
    assert settings.chunk_target_tokens == 220
    assert settings.chunk_max_tokens == 240
    assert settings.chunk_overlap_tokens == 60
    assert settings.minimum_context_score == 0.46
    assert settings.maximum_upload_bytes == 50 * 1024 * 1024
    assert settings.generation_enabled is False
    assert settings.generation_configuration_ready is False


def test_csv_cors_origins_are_parsed(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path,
        cors_origins="http://localhost:3000, https://example.test",
    )

    assert settings.cors_origins == ["http://localhost:3000", "https://example.test"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chunk_target_tokens": 241}, "must not exceed chunk_max_tokens"),
        ({"chunk_max_tokens": 257}, "must not exceed embedding_max_input_tokens"),
        ({"chunk_overlap_tokens": 220}, "must be smaller"),
        ({"default_top_k": 6, "max_top_k": 5}, "must not exceed max_top_k"),
        ({"database_url": "postgresql://localhost/atlas"}, "requires a sqlite"),
        ({"cors_origins": "file:///tmp"}, "invalid CORS origin"),
    ],
)
def test_invalid_settings_fail_fast(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate({"storage_root": tmp_path, **overrides})


def test_generation_requires_model_and_default_endpoint_key(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="generation_model is required"):
        Settings(_env_file=None, storage_root=tmp_path, generation_enabled=True)

    with pytest.raises(ValidationError, match="generation_api_key is required"):
        Settings(
            _env_file=None,
            storage_root=tmp_path,
            generation_enabled=True,
            generation_model="gpt-test",
        )


def test_local_generation_endpoint_can_be_ready_without_real_key(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path,
        generation_enabled=True,
        generation_model="local-model",
        generation_base_url="http://127.0.0.1:11434/v1",
    )

    assert settings.generation_configuration_ready is True


def test_secret_is_redacted(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path,
        generation_enabled=True,
        generation_model="gpt-test",
        generation_api_key="secret-value",
    )

    assert "secret-value" not in repr(settings)
