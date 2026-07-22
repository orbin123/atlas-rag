from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import new_uuid
from app.db.base import Base, utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','processing','indexed','failed','deleting')",
            name="status_valid",
        ),
        CheckConstraint("source_kind IN ('bootstrap','upload')", name="source_kind_valid"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    original_file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    safe_storage_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    license_note: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    relative_source_path: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list[IngestionJob]] = relationship(back_populates="document")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
        CheckConstraint("character_count >= 0", name="character_count_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_empty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repeated_lines_removed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        CheckConstraint("chunk_index >= 1", name="chunk_index_positive"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
        CheckConstraint("token_count > 0", name="token_count_positive"),
        CheckConstraint("status IN ('pending','indexed','failed')", name="status_valid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vector_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('bootstrap','ingest','delete','reindex','evaluation')",
            name="kind_valid",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="status_valid",
        ),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_valid"),
        CheckConstraint("attempt >= 0 AND max_attempts >= 1", name="attempts_valid"),
        Index("ix_ingestion_jobs_claim", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(32))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage_message: Mapped[str | None] = mapped_column(String(512))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document | None] = relationship(back_populates="jobs")


class Query(Base):
    __tablename__ = "queries"
    __table_args__ = (
        CheckConstraint("top_k >= 1", name="top_k_positive"),
        CheckConstraint("minimum_context_score BETWEEN 0 AND 1", name="threshold_valid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    minimum_context_score: Mapped[float] = mapped_column(Float, nullable=False)
    index_version: Mapped[str | None] = mapped_column(String(128))
    embedding_model: Mapped[str] = mapped_column(String(512), nullable=False)
    generation_model: Mapped[str | None] = mapped_column(String(512))
    insufficient_context: Mapped[bool] = mapped_column(Boolean, nullable=False)
    insufficient_reason: Mapped[str | None] = mapped_column(String(255))
    retrieval_latency_ms: Mapped[float | None] = mapped_column(Float)
    generation_latency_ms: Mapped[float | None] = mapped_column(Float)
    total_latency_ms: Mapped[float | None] = mapped_column(Float)
    citation_valid: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    sources: Mapped[list[QuerySource]] = relationship(
        back_populates="query", cascade="all, delete-orphan", passive_deletes=True
    )


class QuerySource(Base):
    __tablename__ = "query_sources"
    __table_args__ = (
        UniqueConstraint("query_id", "rank"),
        CheckConstraint("rank >= 1", name="rank_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    query_id: Mapped[str] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    document_name: Mapped[str] = mapped_column(String(512), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    displayed_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    query: Mapped[Query] = relationship(back_populates="sources")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("mode IN ('retrieval','generation')", name="mode_valid"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="status_valid",
        ),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_valid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    index_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (UniqueConstraint("run_id", "evaluation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_document_name: Mapped[str | None] = mapped_column(String(512))
    expected_page_number: Mapped[int | None] = mapped_column(Integer)
    first_relevant_rank: Mapped[int | None] = mapped_column(Integer)
    recall_at_1: Mapped[bool | None] = mapped_column(Boolean)
    recall_at_3: Mapped[bool | None] = mapped_column(Boolean)
    recall_at_5: Mapped[bool | None] = mapped_column(Boolean)
    recall_at_10: Mapped[bool | None] = mapped_column(Boolean)
    mrr_contribution: Mapped[float | None] = mapped_column(Float)
    top_score: Mapped[float | None] = mapped_column(Float)
    top_document_name: Mapped[str | None] = mapped_column(String(512))
    top_page_number: Mapped[int | None] = mapped_column(Integer)
    retrieval_latency_ms: Mapped[float | None] = mapped_column(Float)
    generated_answer: Mapped[str | None] = mapped_column(Text)
    citation_valid: Mapped[bool | None] = mapped_column(Boolean)
    fallback_correct: Mapped[bool | None] = mapped_column(Boolean)
    answer_correctness: Mapped[float | None] = mapped_column(Float)
    groundedness: Mapped[float | None] = mapped_column(Float)
    failure_category: Mapped[str | None] = mapped_column(String(64), index=True)
    failure_summary: Mapped[str | None] = mapped_column(Text)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")


class UploadedEvaluationCase(Base):
    """A user-authored retrieval case attached to an uploaded document."""

    __tablename__ = "uploaded_evaluation_cases"
    __table_args__ = (UniqueConstraint("document_id", "question"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class IndexState(Base):
    __tablename__ = "index_state"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    index_version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    filesystem_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    faiss_type: Mapped[str] = mapped_column(String(128), nullable=False)
    vector_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    normalization: Mapped[str] = mapped_column(String(32), nullable=False)
    chunking_configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    build_reason: Mapped[str] = mapped_column(String(255), nullable=False)
