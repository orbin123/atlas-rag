from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from app.core.config import Settings


class EmbeddingEncoder(Protocol):
    @property
    def tokenizer(self) -> Any: ...

    def encode(self, texts: Sequence[str], *, batch_size: int) -> Any: ...


class SentenceTransformerEncoder:
    def __init__(self, settings: Settings) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment-specific guard
            raise RuntimeError("Install the backend 'ml' extra to build embeddings.") from exc
        self._settings = settings
        self._model = SentenceTransformer(
            settings.embedding_model,
            revision=settings.embedding_revision,
        )
        self._model.max_seq_length = settings.embedding_max_input_tokens

    @property
    def tokenizer(self) -> Any:
        return self._model.tokenizer

    def encode(self, texts: Sequence[str], *, batch_size: int) -> Any:
        return self._model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self._settings.embedding_normalize,
            show_progress_bar=True,
        )


EncoderFactory = Callable[[Settings], EmbeddingEncoder]


class EmbeddingService:
    """One lazily loaded embedding encoder shared by worker and query services."""

    def __init__(
        self,
        settings: Settings,
        encoder_factory: EncoderFactory = SentenceTransformerEncoder,
    ) -> None:
        self.settings = settings
        self._encoder_factory = encoder_factory
        self._encoder: EmbeddingEncoder | None = None
        self._load_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._encoder is not None

    @property
    def encoder(self) -> EmbeddingEncoder:
        if self._encoder is None:
            raise RuntimeError("The embedding model has not been loaded.")
        return self._encoder

    async def load(self) -> EmbeddingEncoder:
        if self._encoder is not None:
            return self._encoder
        async with self._load_lock:
            if self._encoder is None:
                self._encoder = await asyncio.to_thread(self._encoder_factory, self.settings)
        return self._encoder

    async def encode(self, texts: Sequence[str], *, batch_size: int = 32) -> Any:
        encoder = await self.load()
        return await asyncio.to_thread(
            validated_embeddings,
            encoder,
            texts,
            self.settings,
            batch_size=batch_size,
        )


def validated_embeddings(
    encoder: EmbeddingEncoder,
    texts: Sequence[str],
    settings: Settings,
    *,
    batch_size: int = 32,
) -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to build embeddings.") from exc
    vectors = np.asarray(encoder.encode(texts, batch_size=batch_size), dtype=np.float32)
    expected = (len(texts), settings.embedding_dimension)
    if vectors.shape != expected:
        raise ValueError(f"Embedding shape {vectors.shape} does not match {expected}.")
    if not np.isfinite(vectors).all():
        raise ValueError("Embeddings contain non-finite values.")
    norms = np.linalg.norm(vectors, axis=1)
    if settings.embedding_normalize and not np.allclose(norms, 1.0, atol=1e-4):
        raise ValueError("Embeddings are not L2-normalized.")
    return cast(Any, np.ascontiguousarray(vectors, dtype=np.float32))
