"""Store evaluation questions authored during document upload.

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0004"
down_revision: str | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploaded_evaluation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "question", name="uq_uploaded_evaluation_cases_document_id"),
    )
    op.create_index(
        op.f("ix_uploaded_evaluation_cases_document_id"),
        "uploaded_evaluation_cases",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_uploaded_evaluation_cases_document_id"), "uploaded_evaluation_cases")
    op.drop_table("uploaded_evaluation_cases")
