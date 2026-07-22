from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import CamelModel, PaginatedResponse


class DocumentSummary(CamelModel):
    id: str
    name: str
    file_type: str
    mime_type: str
    domain: str
    page_count: int
    chunk_count: int
    created_at: datetime
    indexed_at: datetime | None
    status: str
    size_bytes: int
    author: str | None
    description: str | None
    source_url: str | None
    license_note: str | None


class DocumentFailure(CamelModel):
    code: str
    message: str


class DocumentEmbedding(CamelModel):
    model: str
    revision: str
    dimension: int


class DocumentDetailResponse(DocumentSummary):
    title: str | None
    source_kind: str
    relative_source_path: str | None
    failure: DocumentFailure | None
    active_job_id: str | None
    updated_at: datetime
    index_version: str | None
    embedding: DocumentEmbedding


class CountItem(CamelModel):
    value: str
    count: int


class IndexHealth(CamelModel):
    status: Literal["ready", "not_ready", "inconsistent"]
    vector_count: int


class DocumentStatsResponse(CamelModel):
    total_documents: int
    total_pages: int
    total_chunks: int
    indexed_documents: int
    processing_documents: int
    failed_documents: int
    deleting_documents: int
    domain_counts: list[CountItem]
    file_type_counts: list[CountItem]
    index_health: IndexHealth


class DocumentPageResponse(CamelModel):
    id: str
    document_id: str
    page_number: int
    text: str
    text_kind: Literal["cleaned", "raw"]
    character_count: int
    is_empty: bool
    repeated_lines_removed: list[str]


class DocumentChunkResponse(CamelModel):
    id: str
    document_id: str
    document_name: str
    chunk_index: int
    page_number: int
    text: str
    token_count: int
    status: str
    embedding_dimension: int


DocumentListResponse = PaginatedResponse[DocumentSummary]
DocumentPageListResponse = PaginatedResponse[DocumentPageResponse]
DocumentChunkListResponse = PaginatedResponse[DocumentChunkResponse]
