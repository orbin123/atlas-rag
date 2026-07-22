from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
# Keep configuration tied to the backend package rather than the command's CWD.
BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Validated runtime configuration.

    Values deliberately bind the Phase 0 model/chunk/threshold decision. A
    deployment cannot silently configure chunks beyond the embedding model's
    effective input limit.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ENV_FILE,),
        env_file_encoding="utf-8",
        env_prefix="ATLAS_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    database_url: str = "sqlite:///./storage/atlas.db"
    storage_root: Path = Path("./storage")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    max_upload_mb: int = Field(default=50, ge=1, le=2048)

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = DEFAULT_EMBEDDING_REVISION
    embedding_dimension: int = Field(default=384, ge=1)
    embedding_max_input_tokens: int = Field(default=256, ge=8)
    embedding_normalize: bool = True
    embedding_batch_size: int = Field(default=32, ge=1, le=512)

    chunking_version: str = "atlas-page-sentence-v1"
    chunk_target_tokens: int = Field(default=220, ge=2)
    chunk_max_tokens: int = Field(default=240, ge=2)
    chunk_overlap_tokens: int = Field(default=60, ge=0)

    default_top_k: int = Field(default=5, ge=1, le=20)
    max_top_k: int = Field(default=20, ge=1, le=100)
    minimum_context_score: float = Field(default=0.46, ge=0, le=1)
    duplicate_similarity_threshold: float = Field(default=0.97, ge=0, le=1)
    worker_poll_interval_seconds: float = Field(default=0.25, ge=0.05, le=10)
    worker_stale_seconds: int = Field(default=120, ge=10, le=3600)
    snapshot_retention_count: int = Field(default=2, ge=2, le=20)

    generation_enabled: bool = False
    generation_model: str | None = None
    generation_base_url: str = DEFAULT_OPENAI_BASE_URL
    generation_api_key: SecretStr | None = None
    generation_timeout_seconds: int = Field(default=30, ge=1, le=300)
    generation_max_concurrency: int = Field(default=2, ge=1, le=32)
    generation_max_output_tokens: int = Field(default=512, ge=1, le=8192)
    generation_context_max_tokens: int = Field(default=3000, ge=1, le=32768)
    evaluation_generation_max_questions: int = Field(default=10, ge=1, le=100)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "api_host",
        "embedding_model",
        "embedding_revision",
        "chunking_version",
        mode="after",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("database_url")
    @classmethod
    def require_sqlite(cls, value: str) -> str:
        if value == "sqlite://" or value.startswith("sqlite:///"):
            return value
        raise ValueError("Atlas local v1 requires a sqlite:/// database URL")

    @field_validator("storage_root")
    @classmethod
    def require_storage_path(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("storage_root must not be empty")
        if value.exists() and not value.is_dir():
            raise ValueError("storage_root must be a directory")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"invalid CORS origin: {value}")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError(f"CORS origin must not include a path: {value}")
        return values

    @model_validator(mode="after")
    def validate_cross_field_policy(self) -> Self:
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("chunk_target_tokens must not exceed chunk_max_tokens")
        if self.chunk_max_tokens > self.embedding_max_input_tokens:
            raise ValueError("chunk_max_tokens must not exceed embedding_max_input_tokens")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_target_tokens")
        if self.default_top_k > self.max_top_k:
            raise ValueError("default_top_k must not exceed max_top_k")
        if self.generation_context_max_tokens < self.chunk_max_tokens:
            raise ValueError("generation_context_max_tokens must be at least chunk_max_tokens")
        if self.generation_enabled:
            if not self.generation_model or not self.generation_model.strip():
                raise ValueError("generation_model is required when generation is enabled")
            if self._uses_default_openai_endpoint() and not self._has_generation_api_key():
                raise ValueError("generation_api_key is required for the default OpenAI endpoint")
        parsed = urlparse(self.generation_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("generation_base_url must be an absolute HTTP(S) URL")
        return self

    @property
    def maximum_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def generation_configuration_ready(self) -> bool:
        if not self.generation_enabled or not self.generation_model:
            return False
        return not self._uses_default_openai_endpoint() or self._has_generation_api_key()

    def _uses_default_openai_endpoint(self) -> bool:
        return self.generation_base_url.rstrip("/") == DEFAULT_OPENAI_BASE_URL

    def _has_generation_api_key(self) -> bool:
        return bool(self.generation_api_key and self.generation_api_key.get_secret_value().strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
