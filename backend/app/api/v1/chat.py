from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Request
from fastapi import Query as QueryParameter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.api.errors import APIError
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.db.models import (
    Document,
    EvaluationResult,
    IndexState,
    Query,
    QuerySource,
)
from app.schemas.chat import (
    ChatCitation,
    ChatConfig,
    ChatQueryRequest,
    ChatQueryResponse,
    ChatSource,
    ChatTiming,
    RetrievalConfig,
    RetrievalDetailResponse,
    RetrievalTiming,
    Suggestion,
)
from app.services.chat import ChatGenerationError, execute_chat_query
from app.services.evaluation import EvaluationDatasetMissingError, canonical_gold_run
from app.services.generation import GenerationService
from app.services.retrieval import RetrievalService, RetrievedSource

chat_router = APIRouter(prefix="/chat", tags=["chat"])
retrieval_router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _source_schema(source: RetrievedSource) -> ChatSource:
    return ChatSource(
        label=source.label,
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        document_name=source.document_name,
        domain=source.domain,
        page_number=source.page_number,
        chunk_index=source.chunk_index,
        text=source.text,
        token_count=source.token_count,
        similarity_score=source.similarity_score,
        rank=source.rank,
    )


def _snapshot_source_schema(source: QuerySource) -> ChatSource:
    return ChatSource(
        label=f"S{source.rank}",
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        document_name=source.document_name,
        domain=source.domain,
        page_number=source.page_number,
        chunk_index=source.chunk_index,
        text=source.displayed_text,
        token_count=source.token_count,
        similarity_score=source.similarity_score,
        rank=source.rank,
    )


def _active_index(request: Request, session: Session) -> tuple[Any, IndexState]:
    readiness = cast(RuntimeReadiness, request.app.state.readiness)
    state = session.get(IndexState, 1)
    index = getattr(request.app.state, "active_index", None)
    if not readiness.index_consistent and state is not None:
        raise APIError(
            code="INDEX_INCONSISTENT",
            message="The active index failed alignment verification.",
            status_code=503,
            details={"diagnostic": readiness.index_diagnostic},
        )
    if not readiness.index_ready or state is None or index is None:
        raise APIError(
            code="INDEX_NOT_READY",
            message="No verified active retrieval index is available.",
            status_code=503,
        )
    if int(index.ntotal) != state.vector_count or int(index.d) != state.dimension:
        raise APIError(
            code="INDEX_INCONSISTENT",
            message="The in-memory index does not match the active index state.",
            status_code=503,
        )
    return index, state


@chat_router.post(
    "/queries",
    response_model=ChatQueryResponse,
    operation_id="createChatQuery",
)
async def create_chat_query(
    payload: ChatQueryRequest,
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> ChatQueryResponse:
    settings = cast(Settings, request.app.state.settings)
    top_k = payload.top_k or settings.default_top_k
    if top_k > settings.max_top_k:
        raise APIError(
            code="VALIDATION_ERROR",
            message=f"topK must not exceed {settings.max_top_k}.",
            status_code=422,
            details={"maximumTopK": settings.max_top_k},
        )
    index, state = _active_index(request, session)
    retrieval = cast(RetrievalService, request.app.state.retrieval_service)
    generation = cast(GenerationService, request.app.state.generation_service)
    try:
        result = await execute_chat_query(
            session=session,
            index=index,
            state=state,
            settings=settings,
            retrieval=retrieval,
            generation=generation,
            question=payload.question,
            top_k=top_k,
            domain=payload.domain,
        )
    except ChatGenerationError as exc:
        raise APIError(
            code=exc.code,
            message=exc.safe_message,
            status_code=exc.status_code,
            details={"queryId": exc.query_id},
        ) from exc
    except (RuntimeError, ValueError) as exc:
        raise APIError(
            code="INDEX_NOT_READY",
            message="The question could not be embedded against the active index.",
            status_code=503,
        ) from exc

    query = result.query
    source_by_label = {source.label: source for source in result.sources}
    citations = [
        ChatCitation(
            label=label,
            document_id=source_by_label[label].document_id,
            document_name=source_by_label[label].document_name,
            page_number=source_by_label[label].page_number,
            chunk_index=source_by_label[label].chunk_index,
        )
        for label in result.citation_labels
    ]
    return ChatQueryResponse(
        query_id=query.id,
        question=query.question,
        answer=query.answer or "",
        insufficient_context=query.insufficient_context,
        insufficient_reason=query.insufficient_reason,
        citations=citations,
        sources=[_source_schema(source) for source in result.sources],
        timing=ChatTiming(
            retrieval_ms=query.retrieval_latency_ms or 0.0,
            generation_ms=query.generation_latency_ms or 0.0,
            total_ms=query.total_latency_ms or 0.0,
        ),
        config=ChatConfig(
            top_k=query.top_k,
            minimum_context_score=query.minimum_context_score,
            index_version=str(query.index_version),
        ),
    )


@retrieval_router.get(
    "/{queryId}",
    response_model=RetrievalDetailResponse,
    operation_id="getRetrievalDetail",
)
def get_retrieval_detail(
    query_id: Annotated[str, Path(alias="queryId")],
    session: Annotated[Session, Depends(get_database_session)],
) -> RetrievalDetailResponse:
    query = session.get(Query, query_id)
    if query is None:
        raise APIError(
            code="QUERY_NOT_FOUND",
            message="The requested query was not found.",
            status_code=404,
            details={"queryId": query_id},
        )
    sources = session.scalars(
        select(QuerySource).where(QuerySource.query_id == query.id).order_by(QuerySource.rank)
    ).all()
    return RetrievalDetailResponse(
        query_id=query.id,
        question=query.question,
        status=query.status,
        insufficient_context=query.insufficient_context,
        sources=[_snapshot_source_schema(source) for source in sources],
        timing=RetrievalTiming(retrieval_ms=query.retrieval_latency_ms or 0.0),
        config=RetrievalConfig(
            top_k=query.top_k,
            domain=query.domain,
            minimum_context_score=query.minimum_context_score,
            index_version=query.index_version,
        ),
        created_at=query.created_at,
    )


@chat_router.get(
    "/suggestions",
    response_model=list[Suggestion],
    operation_id="listChatSuggestions",
)
def list_chat_suggestions(
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, QueryParameter(ge=1, le=20)] = 4,
) -> list[Suggestion]:
    try:
        run_id = canonical_gold_run(session).id
    except EvaluationDatasetMissingError as exc:
        raise APIError(
            code="EVALUATION_DATASET_MISSING",
            message="No versioned evaluation question set is available.",
            status_code=503,
        ) from exc
    rows = session.scalars(
        select(EvaluationResult)
        .join(
            Document,
            Document.original_file_name == EvaluationResult.expected_document_name,
        )
        .where(
            EvaluationResult.run_id == run_id,
            EvaluationResult.answerable.is_(True),
            Document.status == "indexed",
        )
        .order_by(EvaluationResult.evaluation_id)
        .limit(limit)
    ).all()
    return [
        Suggestion(id=row.evaluation_id, question=row.question, domain=row.domain) for row in rows
    ]
