"""Allow distinct curated paths with identical bytes.

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260720_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_sha256", type_="unique")
        batch_op.create_index("ix_documents_sha256", ["sha256"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_sha256")
        batch_op.create_unique_constraint("uq_documents_sha256", ["sha256"])
