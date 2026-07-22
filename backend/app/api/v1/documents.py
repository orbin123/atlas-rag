from __future__ import annotations

import asyncio
import math
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi import status as http_status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import get_database_session
from app.api.errors import APIError
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.db.models import Chunk, Document, DocumentPage, IndexState, IngestionJob
from app.schemas.document import (
    CountItem,
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentEmbedding,
    DocumentFailure,
    DocumentListResponse,
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentStatsResponse,
    DocumentSummary,
    IndexHealth,
)
from app.schemas.ingestion import AcceptedJobResponse
from app.services.deletions import DeletionAcceptanceError, accept_document_deletion
from app.workers.runner import IngestionWorker

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document(session: Session, document_id: str) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise APIError(
            code="DOCUMENT_NOT_FOUND",
            message="The requested document was not found.",
            status_code=404,
            details={"documentId": document_id},
        )
    return document


def _summary(document: Document) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        name=document.original_file_name,
        file_type=document.file_type,
        mime_type=document.mime_type,
        domain=document.domain,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
        indexed_at=document.indexed_at,
        status=document.status,
        size_bytes=document.size_bytes,
        author=document.author,
        description=document.description,
        source_url=document.source_url,
        license_note=document.license_note,
    )


def _total_pages(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0


@router.get("", response_model=DocumentListResponse, operation_id="listDocuments")
def list_documents(
    session: Annotated[Session, Depends(get_database_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=200)] = None,
    domain: Annotated[str | None, Query(max_length=255)] = None,
    file_type: Annotated[str | None, Query(alias="fileType", max_length=16)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    sort: Literal[
        "name",
        "domain",
        "createdAt",
        "indexedAt",
        "sizeBytes",
        "pageCount",
        "chunkCount",
    ] = "createdAt",
    order: Literal["asc", "desc"] = "desc",
) -> DocumentListResponse:
    conditions = []
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                Document.original_file_name.ilike(pattern),
                Document.title.ilike(pattern),
                Document.description.ilike(pattern),
            )
        )
    if domain:
        conditions.append(Document.domain == domain)
    if file_type:
        conditions.append(Document.file_type == file_type.lower())
    if status:
        conditions.append(Document.status == status)
    count_statement = select(func.count()).select_from(Document).where(*conditions)
    total = int(session.scalar(count_statement) or 0)
    sort_columns = {
        "name": Document.original_file_name,
        "domain": Document.domain,
        "createdAt": Document.created_at,
        "indexedAt": Document.indexed_at,
        "sizeBytes": Document.size_bytes,
        "pageCount": Document.page_count,
        "chunkCount": Document.chunk_count,
    }
    ordering = asc if order == "asc" else desc
    rows = session.scalars(
        select(Document)
        .where(*conditions)
        .order_by(ordering(sort_columns[sort]), asc(Document.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentListResponse(
        items=[_summary(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=_total_pages(total, page_size),
    )


@router.get("/stats", response_model=DocumentStatsResponse, operation_id="getDocumentStats")
def get_document_stats(
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> DocumentStatsResponse:
    def count(
        model: type[Document] | type[DocumentPage] | type[Chunk],
        *where: ColumnElement[bool],
    ) -> int:
        statement = select(func.count()).select_from(model)
        if where:
            statement = statement.where(*where)
        return int(session.scalar(statement) or 0)

    domain_counts = session.execute(
        select(Document.domain, func.count()).group_by(Document.domain).order_by(Document.domain)
    ).all()
    file_counts = session.execute(
        select(Document.file_type, func.count())
        .group_by(Document.file_type)
        .order_by(Document.file_type)
    ).all()
    state = session.get(IndexState, 1)
    runtime = cast(RuntimeReadiness, request.app.state.readiness)
    if runtime.index_ready and runtime.index_consistent and state:
        health_status = "ready"
    elif state and not runtime.index_consistent:
        health_status = "inconsistent"
    else:
        health_status = "not_ready"
    return DocumentStatsResponse(
        total_documents=count(Document),
        total_pages=count(DocumentPage),
        total_chunks=count(Chunk),
        indexed_documents=count(Document, Document.status == "indexed"),
        processing_documents=count(Document, Document.status.in_(["queued", "processing"])),
        failed_documents=count(Document, Document.status == "failed"),
        deleting_documents=count(Document, Document.status == "deleting"),
        domain_counts=[
            CountItem(value=str(value), count=int(total)) for value, total in domain_counts
        ],
        file_type_counts=[
            CountItem(value=str(value), count=int(total)) for value, total in file_counts
        ],
        index_health=IndexHealth(
            status=health_status,
            vector_count=state.vector_count if state else 0,
        ),
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse, operation_id="getDocument")
def get_document(
    document_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> DocumentDetailResponse:
    document = _get_document(session, document_id)
    active_job_id = session.scalar(
        select(IngestionJob.id)
        .where(
            IngestionJob.document_id == document_id,
            IngestionJob.status.in_(["queued", "running"]),
        )
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    state = session.get(IndexState, 1)
    settings = cast(Settings, request.app.state.settings)
    return DocumentDetailResponse(
        **_summary(document).model_dump(),
        title=document.title,
        source_kind=document.source_kind,
        relative_source_path=document.relative_source_path,
        failure=(
            DocumentFailure(code=document.failure_code, message=document.failure_message)
            if document.failure_code and document.failure_message
            else None
        ),
        active_job_id=active_job_id,
        updated_at=document.updated_at,
        index_version=state.index_version if state and document.status == "indexed" else None,
        embedding=DocumentEmbedding(
            model=settings.embedding_model,
            revision=settings.embedding_revision,
            dimension=settings.embedding_dimension,
        ),
    )


@router.delete(
    "/{document_id}",
    response_model=AcceptedJobResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    operation_id="deleteDocument",
)
async def delete_document(document_id: str, request: Request) -> AcceptedJobResponse:
    readiness = cast(RuntimeReadiness, request.app.state.readiness)
    if not readiness.worker_ready:
        raise APIError(
            code="WORKER_NOT_READY",
            message="The durable worker is not ready to accept deletions.",
            status_code=503,
        )
    if not readiness.index_consistent or not readiness.index_ready:
        raise APIError(
            code="INDEX_NOT_READY",
            message="The active index is not verified for document deletion.",
            status_code=503,
        )
    settings = cast(Settings, request.app.state.settings)
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    worker = cast(IngestionWorker, request.app.state.ingestion_worker)
    try:
        accepted = await asyncio.to_thread(
            accept_document_deletion,
            document_id,
            settings,
            factory,
        )
    except DeletionAcceptanceError as exc:
        raise APIError(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        ) from exc
    worker.kick()
    return AcceptedJobResponse(
        job_id=accepted.job_id,
        document_id=accepted.document_id,
        status=accepted.status,
        status_url=f"/api/v1/ingestion-jobs/{accepted.job_id}",
    )


@router.get(
    "/{document_id}/pages",
    response_model=DocumentPageListResponse,
    operation_id="listDocumentPages",
)
def list_document_pages(
    document_id: str,
    session: Annotated[Session, Depends(get_database_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    text: Literal["cleaned", "raw"] = "cleaned",
) -> DocumentPageListResponse:
    _get_document(session, document_id)
    total = int(
        session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document_id)
        )
        or 0
    )
    rows = session.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentPageListResponse(
        items=[
            DocumentPageResponse(
                id=row.id,
                document_id=row.document_id,
                page_number=row.page_number,
                text=row.cleaned_text if text == "cleaned" else row.raw_text,
                text_kind=text,
                character_count=(len(row.cleaned_text) if text == "cleaned" else len(row.raw_text)),
                is_empty=row.is_empty,
                repeated_lines_removed=row.repeated_lines_removed,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=_total_pages(total, page_size),
    )


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    operation_id="listDocumentChunks",
)
def list_document_chunks(
    document_id: str,
    session: Annotated[Session, Depends(get_database_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> DocumentChunkListResponse:
    document = _get_document(session, document_id)
    conditions = [Chunk.document_id == document_id]
    if search and search.strip():
        conditions.append(Chunk.cleaned_text.ilike(f"%{search.strip()}%"))
    total = int(session.scalar(select(func.count()).select_from(Chunk).where(*conditions)) or 0)
    rows = session.scalars(
        select(Chunk)
        .where(*conditions)
        .order_by(Chunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentChunkListResponse(
        items=[
            DocumentChunkResponse(
                id=row.id,
                document_id=row.document_id,
                document_name=document.original_file_name,
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                text=row.original_text,
                token_count=row.token_count,
                status=row.status,
                embedding_dimension=row.embedding_dimension,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=_total_pages(total, page_size),
    )
