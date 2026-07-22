from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ids import new_uuid
from app.db.models import IndexState, Query, QuerySource
from app.services.generation import (
    GenerationInvalidResponseError,
    GenerationProviderError,
    GenerationService,
    GenerationTimeoutError,
    GenerationUnavailableError,
)
from app.services.prompting import build_grounded_messages
from app.services.retrieval import RetrievalService, RetrievedSource

INSUFFICIENT_CONTEXT_ANSWER = (
    "I don't have enough evidence in the indexed documents to answer that question."
)
INSUFFICIENT_CONTEXT_REASON = "No retrieved source met the minimum context score."


@dataclass(frozen=True, slots=True)
class ChatResult:
    query: Query
    sources: tuple[RetrievedSource, ...]
    citation_labels: tuple[str, ...]


class ChatGenerationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int, query_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        self.query_id = query_id


def _persist_sources(session: Session, query_id: str, sources: tuple[RetrievedSource, ...]) -> None:
    for source in sources:
        session.add(
            QuerySource(
                query_id=query_id,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                rank=source.rank,
                similarity_score=source.similarity_score,
                document_name=source.document_name,
                domain=source.domain,
                page_number=source.page_number,
                chunk_index=source.chunk_index,
                displayed_text=source.text,
                token_count=source.token_count,
            )
        )


def _generation_failure(exc: Exception, query_id: str) -> ChatGenerationError:
    if isinstance(exc, GenerationUnavailableError):
        return ChatGenerationError(
            "GENERATION_PROVIDER_UNAVAILABLE",
            "Generation is disabled or not configured for this Atlas instance.",
            503,
            query_id,
        )
    if isinstance(exc, GenerationTimeoutError):
        return ChatGenerationError(
            "GENERATION_TIMEOUT", "The generation provider timed out.", 504, query_id
        )
    if isinstance(exc, GenerationInvalidResponseError):
        return ChatGenerationError(
            "GENERATION_RESPONSE_INVALID",
            "The generation provider did not return a grounded answer with valid citations.",
            502,
            query_id,
        )
    if isinstance(exc, GenerationProviderError):
        return ChatGenerationError(
            "GENERATION_PROVIDER_ERROR",
            "The generation provider request failed.",
            503,
            query_id,
        )
    raise exc


async def execute_chat_query(
    *,
    session: Session,
    index: Any,
    state: IndexState,
    settings: Settings,
    retrieval: RetrievalService,
    generation: GenerationService,
    question: str,
    top_k: int,
    domain: str | None,
) -> ChatResult:
    total_started = time.perf_counter()
    retrieved = await retrieval.retrieve(
        session=session,
        index=index,
        question=question,
        top_k=top_k,
        domain=domain,
    )
    sources = retrieved.sources
    insufficient = not sources or sources[0].similarity_score < settings.minimum_context_score
    query = Query(
        id=new_uuid(),
        question=question,
        answer=INSUFFICIENT_CONTEXT_ANSWER if insufficient else None,
        status="insufficient_context" if insufficient else "retrieved",
        top_k=top_k,
        domain=domain,
        minimum_context_score=settings.minimum_context_score,
        index_version=state.index_version,
        embedding_model=settings.embedding_model,
        generation_model=settings.generation_model,
        insufficient_context=insufficient,
        insufficient_reason=INSUFFICIENT_CONTEXT_REASON if insufficient else None,
        retrieval_latency_ms=retrieved.latency_ms,
        generation_latency_ms=0.0 if insufficient else None,
        total_latency_ms=(time.perf_counter() - total_started) * 1000 if insufficient else None,
        citation_valid=None if insufficient else False,
    )
    session.add(query)
    _persist_sources(session, query.id, sources)
    session.commit()
    if insufficient:
        session.refresh(query)
        return ChatResult(query=query, sources=sources, citation_labels=())

    messages, prompt_sources = build_grounded_messages(
        question,
        sources,
        token_budget=settings.generation_context_max_tokens,
    )
    generation_started = time.perf_counter()
    try:
        answer, validation = await generation.generate_validated(
            messages,
            allowed_labels=[source.label for source in prompt_sources],
        )
    except (
        GenerationUnavailableError,
        GenerationTimeoutError,
        GenerationProviderError,
        GenerationInvalidResponseError,
    ) as exc:
        generation_ms = (time.perf_counter() - generation_started) * 1000
        query.status = "generation_failed"
        query.generation_latency_ms = generation_ms
        query.total_latency_ms = (time.perf_counter() - total_started) * 1000
        query.citation_valid = False
        session.commit()
        raise _generation_failure(exc, query.id) from exc

    query.answer = answer
    query.status = "completed"
    query.generation_latency_ms = (time.perf_counter() - generation_started) * 1000
    query.total_latency_ms = (time.perf_counter() - total_started) * 1000
    query.citation_valid = True
    session.commit()
    session.refresh(query)
    return ChatResult(query=query, sources=sources, citation_labels=validation.labels)
