from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.db.models import Chunk, Document, DocumentPage, IndexState
from app.schemas.system import (
    CapabilityInfo,
    ChunkingInfo,
    CorpusInfo,
    EmbeddingInfo,
    GenerationInfo,
    IndexInfo,
    RetrievalInfo,
    SystemInfoResponse,
)

router = APIRouter(prefix="/system", tags=["system"])


def _count(session: Session, model: type[Document] | type[DocumentPage] | type[Chunk]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


@router.get("/info", response_model=SystemInfoResponse, operation_id="getSystemInfo")
def get_system_info(
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> SystemInfoResponse:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(RuntimeReadiness, request.app.state.readiness)
    index_state = session.get(IndexState, 1)
    index_ready = runtime.index_ready and runtime.index_consistent and index_state is not None
    return SystemInfoResponse(
        corpus=CorpusInfo(
            document_count=_count(session, Document),
            page_count=_count(session, DocumentPage),
            chunk_count=_count(session, Chunk),
        ),
        index=IndexInfo(
            status="ready" if index_ready else "not_ready",
            type=index_state.faiss_type if index_state else "IndexIDMap2/IndexFlatIP",
            version=index_state.index_version if index_state else None,
            vector_count=index_state.vector_count if index_state else 0,
            dimension=index_state.dimension if index_state else settings.embedding_dimension,
        ),
        embedding=EmbeddingInfo(
            model=settings.embedding_model,
            revision=settings.embedding_revision,
            dimension=settings.embedding_dimension,
            max_input_tokens=settings.embedding_max_input_tokens,
        ),
        chunking=ChunkingInfo(
            version=settings.chunking_version,
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
        retrieval=RetrievalInfo(
            default_top_k=settings.default_top_k,
            maximum_top_k=settings.max_top_k,
            minimum_context_score=settings.minimum_context_score,
            duplicate_similarity_threshold=settings.duplicate_similarity_threshold,
            reranker_enabled=False,
        ),
        generation=GenerationInfo(
            enabled=settings.generation_enabled,
            ready=settings.generation_configuration_ready,
            provider="openai",
            model=settings.generation_model,
            timeout_seconds=settings.generation_timeout_seconds,
            maximum_concurrent_requests=settings.generation_max_concurrency,
        ),
        capabilities=CapabilityInfo(
            ocr=False,
            supported_file_types=["pdf", "docx", "txt"],
            maximum_upload_bytes=settings.maximum_upload_bytes,
        ),
    )
