from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Chunk, Document
from app.services.embedding import EmbeddingService


@dataclass(frozen=True, slots=True)
class RetrievedSource:
    chunk_id: str
    document_id: str
    document_name: str
    domain: str
    page_number: int
    chunk_index: int
    text: str
    token_count: int
    similarity_score: float
    rank: int
    vector_id: int

    @property
    def label(self) -> str:
        return f"S{self.rank}"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    sources: tuple[RetrievedSource, ...]
    latency_ms: float


class RetrievalService:
    """Canonical semantic retrieval used by chat and later evaluation runs."""

    def __init__(self, settings: Settings, embeddings: EmbeddingService) -> None:
        self.settings = settings
        self.embeddings = embeddings

    async def retrieve(
        self,
        *,
        session: Session,
        index: Any,
        question: str,
        top_k: int,
        domain: str | None = None,
    ) -> RetrievalResult:
        if top_k < 1 or top_k > self.settings.max_top_k:
            raise ValueError(f"top_k must be between 1 and {self.settings.max_top_k}")
        started = time.perf_counter()
        query_vector = await self.embeddings.encode([question], batch_size=1)
        total = int(index.ntotal)
        if total == 0:
            return RetrievalResult((), (time.perf_counter() - started) * 1000)

        candidate_count = min(total, max(20, top_k * 4))
        selected: list[tuple[Any, float, Any]] = []
        while True:
            scores, identifiers = index.search(query_vector, candidate_count)
            ranked = [
                (int(vector_id), float(score))
                for vector_id, score in zip(identifiers[0], scores[0], strict=True)
                if int(vector_id) >= 0
            ]
            rows = self._load_candidates(session, [vector_id for vector_id, _ in ranked])
            selected = self._select_distinct(index, ranked, rows, domain, top_k)
            if len(selected) >= top_k or candidate_count >= total:
                break
            candidate_count = min(total, candidate_count * 2)

        sources = tuple(
            RetrievedSource(
                chunk_id=row.Chunk.id,
                document_id=row.Document.id,
                document_name=row.Document.original_file_name,
                domain=row.Document.domain,
                page_number=row.Chunk.page_number,
                chunk_index=row.Chunk.chunk_index,
                text=row.Chunk.original_text,
                token_count=row.Chunk.token_count,
                similarity_score=max(0.0, min(1.0, score)),
                rank=rank,
                vector_id=row.Chunk.vector_id,
            )
            for rank, (row, score, _) in enumerate(selected, start=1)
        )
        return RetrievalResult(sources, (time.perf_counter() - started) * 1000)

    @staticmethod
    def _load_candidates(session: Session, vector_ids: list[int]) -> dict[int, Any]:
        rows: dict[int, Any] = {}
        for offset in range(0, len(vector_ids), 500):
            batch = vector_ids[offset : offset + 500]
            for row in session.execute(
                select(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.vector_id.in_(batch),
                    Chunk.status == "indexed",
                    Document.status == "indexed",
                )
            ):
                rows[int(row.Chunk.vector_id)] = row
        return rows

    def _select_distinct(
        self,
        index: Any,
        ranked: list[tuple[int, float]],
        rows: dict[int, Any],
        domain: str | None,
        top_k: int,
    ) -> list[tuple[Any, float, Any]]:
        import numpy as np

        selected: list[tuple[Any, float, Any]] = []
        selected_vectors: list[Any] = []
        for vector_id, score in ranked:
            row = rows.get(vector_id)
            if row is None or (domain is not None and row.Document.domain != domain):
                continue
            vector = np.asarray(index.reconstruct(vector_id), dtype=np.float32)
            if any(
                float(np.dot(vector, previous)) >= self.settings.duplicate_similarity_threshold
                for previous in selected_vectors
            ):
                continue
            selected.append((row, score, vector))
            selected_vectors.append(vector)
            if len(selected) == top_k:
                break
        return selected
