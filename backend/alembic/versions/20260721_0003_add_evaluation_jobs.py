"""Allow durable evaluation jobs in the local worker queue.

Revision ID: 20260721_0003
Revises: 20260720_0002
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_ingestion_jobs_kind_valid"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_ingestion_jobs_kind_valid"),
            "kind IN ('bootstrap','ingest','delete','reindex','evaluation')",
        )


def downgrade() -> None:
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_ingestion_jobs_kind_valid"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_ingestion_jobs_kind_valid"),
            "kind IN ('bootstrap','ingest','delete','reindex')",
        )
