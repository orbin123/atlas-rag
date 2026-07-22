"""Create the durable Atlas metadata schema.

Revision ID: 20260720_0001
Revises: None
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("original_file_name", sa.String(512), nullable=False),
        sa.Column("safe_storage_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512)),
        sa.Column("author", sa.String(512)),
        sa.Column("description", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("license_note", sa.Text()),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("relative_source_path", sa.Text()),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','processing','indexed','failed','deleting')",
            name=op.f("ck_documents_status_valid"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('bootstrap','upload')",
            name=op.f("ck_documents_source_kind_valid"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_documents_size_nonnegative")),
        sa.UniqueConstraint("safe_storage_name", name=op.f("uq_documents_safe_storage_name")),
        sa.UniqueConstraint("sha256", name=op.f("uq_documents_sha256")),
    )
    op.create_index(op.f("ix_documents_domain"), "documents", ["domain"])
    op.create_index(op.f("ix_documents_file_type"), "documents", ["file_type"])
    op.create_index(op.f("ix_documents_status"), "documents", ["status"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("is_empty", sa.Boolean(), nullable=False),
        sa.Column("repeated_lines_removed", sa.JSON(), nullable=False),
        sa.CheckConstraint("page_number >= 1", name=op.f("ck_document_pages_page_number_positive")),
        sa.CheckConstraint(
            "character_count >= 0",
            name=op.f("ck_document_pages_character_count_nonnegative"),
        ),
        sa.UniqueConstraint(
            "document_id", "page_number", name=op.f("uq_document_pages_document_id")
        ),
    )
    op.create_index(op.f("ix_document_pages_document_id"), "document_pages", ["document_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vector_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(512), nullable=False),
        sa.Column("embedding_revision", sa.String(128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("chunk_index >= 1", name=op.f("ck_chunks_chunk_index_positive")),
        sa.CheckConstraint("page_number >= 1", name=op.f("ck_chunks_page_number_positive")),
        sa.CheckConstraint("token_count > 0", name=op.f("ck_chunks_token_count_positive")),
        sa.CheckConstraint(
            "status IN ('pending','indexed','failed')", name=op.f("ck_chunks_status_valid")
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name=op.f("uq_chunks_document_id")),
        sa.UniqueConstraint("vector_id", name=op.f("uq_chunks_vector_id")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"])
    op.create_index(op.f("ix_chunks_status"), "chunks", ["status"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32)),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("stage_message", sa.String(512)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("result", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('bootstrap','ingest','delete','reindex')",
            name=op.f("ck_ingestion_jobs_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name=op.f("ck_ingestion_jobs_status_valid"),
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name=op.f("ck_ingestion_jobs_progress_valid"),
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1",
            name=op.f("ck_ingestion_jobs_attempts_valid"),
        ),
    )
    op.create_index(op.f("ix_ingestion_jobs_document_id"), "ingestion_jobs", ["document_id"])
    op.create_index(op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_claim", "ingestion_jobs", ["status", "created_at"])

    op.create_table(
        "queries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("minimum_context_score", sa.Float(), nullable=False),
        sa.Column("index_version", sa.String(128)),
        sa.Column("embedding_model", sa.String(512), nullable=False),
        sa.Column("generation_model", sa.String(512)),
        sa.Column("insufficient_context", sa.Boolean(), nullable=False),
        sa.Column("insufficient_reason", sa.String(255)),
        sa.Column("retrieval_latency_ms", sa.Float()),
        sa.Column("generation_latency_ms", sa.Float()),
        sa.Column("total_latency_ms", sa.Float()),
        sa.Column("citation_valid", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("top_k >= 1", name=op.f("ck_queries_top_k_positive")),
        sa.CheckConstraint(
            "minimum_context_score BETWEEN 0 AND 1",
            name=op.f("ck_queries_threshold_valid"),
        ),
    )
    op.create_index(op.f("ix_queries_created_at"), "queries", ["created_at"])

    op.create_table(
        "query_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "query_id",
            sa.String(36),
            sa.ForeignKey("queries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("document_name", sa.String(512), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("displayed_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("rank >= 1", name=op.f("ck_query_sources_rank_positive")),
        sa.UniqueConstraint("query_id", "rank", name=op.f("uq_query_sources_query_id")),
    )
    op.create_index(op.f("ix_query_sources_query_id"), "query_sources", ["query_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36)),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("dataset_hash", sa.String(64), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("index_version", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("evaluated_questions", sa.Integer(), nullable=False),
        sa.Column("summary_metrics", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "mode IN ('retrieval','generation')", name=op.f("ck_evaluation_runs_mode_valid")
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name=op.f("ck_evaluation_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name=op.f("ck_evaluation_runs_progress_valid"),
        ),
    )
    op.create_index(op.f("ix_evaluation_runs_created_at"), "evaluation_runs", ["created_at"])
    op.create_index(op.f("ix_evaluation_runs_job_id"), "evaluation_runs", ["job_id"])
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evaluation_id", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answerable", sa.Boolean(), nullable=False),
        sa.Column("expected_document_name", sa.String(512)),
        sa.Column("expected_page_number", sa.Integer()),
        sa.Column("first_relevant_rank", sa.Integer()),
        sa.Column("recall_at_1", sa.Boolean()),
        sa.Column("recall_at_3", sa.Boolean()),
        sa.Column("recall_at_5", sa.Boolean()),
        sa.Column("recall_at_10", sa.Boolean()),
        sa.Column("mrr_contribution", sa.Float()),
        sa.Column("top_score", sa.Float()),
        sa.Column("top_document_name", sa.String(512)),
        sa.Column("top_page_number", sa.Integer()),
        sa.Column("retrieval_latency_ms", sa.Float()),
        sa.Column("generated_answer", sa.Text()),
        sa.Column("citation_valid", sa.Boolean()),
        sa.Column("fallback_correct", sa.Boolean()),
        sa.Column("answer_correctness", sa.Float()),
        sa.Column("groundedness", sa.Float()),
        sa.Column("failure_category", sa.String(64)),
        sa.Column("failure_summary", sa.Text()),
        sa.UniqueConstraint("run_id", "evaluation_id", name=op.f("uq_evaluation_results_run_id")),
    )
    op.create_index(op.f("ix_evaluation_results_domain"), "evaluation_results", ["domain"])
    op.create_index(
        op.f("ix_evaluation_results_failure_category"),
        "evaluation_results",
        ["failure_category"],
    )
    op.create_index(op.f("ix_evaluation_results_run_id"), "evaluation_results", ["run_id"])

    op.create_table(
        "index_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("index_version", sa.String(128), nullable=False),
        sa.Column("filesystem_path", sa.Text(), nullable=False),
        sa.Column("manifest_checksum", sa.String(64), nullable=False),
        sa.Column("faiss_type", sa.String(128), nullable=False),
        sa.Column("vector_count", sa.BigInteger(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(512), nullable=False),
        sa.Column("embedding_revision", sa.String(128), nullable=False),
        sa.Column("normalization", sa.String(32), nullable=False),
        sa.Column("chunking_configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("build_reason", sa.String(255), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_index_state_singleton")),
        sa.UniqueConstraint("index_version", name=op.f("uq_index_state_index_version")),
    )


def downgrade() -> None:
    op.drop_table("index_state")
    op.drop_index(op.f("ix_evaluation_results_run_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_failure_category"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_domain"), table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index(op.f("ix_evaluation_runs_status"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_job_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_created_at"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(op.f("ix_query_sources_query_id"), table_name="query_sources")
    op.drop_table("query_sources")
    op.drop_index(op.f("ix_queries_created_at"), table_name="queries")
    op.drop_table("queries")
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_document_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index(op.f("ix_chunks_status"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_document_pages_document_id"), table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_file_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_domain"), table_name="documents")
    op.drop_table("documents")
