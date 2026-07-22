from __future__ import annotations

from dataclasses import dataclass

from filelock import FileLock
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.ids import new_uuid
from app.db.models import Document, IngestionJob


class DeletionAcceptanceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True, slots=True)
class AcceptedDeletion:
    job_id: str
    document_id: str
    status: str


def accept_document_deletion(
    document_id: str,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> AcceptedDeletion:
    """Durably enqueue an idempotent coordinated deletion request."""

    lock = FileLock(settings.storage_root / "deletion-accept.lock")
    with lock, session_factory.begin() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise DeletionAcceptanceError(
                "DOCUMENT_NOT_FOUND",
                "The requested document was not found.",
                404,
                {"documentId": document_id},
            )
        active = session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.kind == "delete",
                IngestionJob.status.in_(["queued", "running"]),
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(1)
        )
        if active is not None:
            document.status = "deleting"
            return AcceptedDeletion(active.id, document_id, active.status)
        conflicting = session.scalar(
            select(IngestionJob.id)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.kind == "ingest",
                IngestionJob.status.in_(["queued", "running"]),
            )
            .limit(1)
        )
        if conflicting is not None or document.status in {"queued", "processing"}:
            raise DeletionAcceptanceError(
                "DOCUMENT_STATE_CONFLICT",
                "The document cannot be deleted while ingestion is active.",
                409,
                {"documentId": document_id},
            )
        if document.status not in {"indexed", "failed", "deleting"}:
            raise DeletionAcceptanceError(
                "DOCUMENT_STATE_CONFLICT",
                "The document is not in a deletable state.",
                409,
                {"documentId": document_id},
            )
        job_id = new_uuid()
        document.status = "deleting"
        document.failure_code = None
        document.failure_message = None
        session.add(
            IngestionJob(
                id=job_id,
                document_id=document_id,
                kind="delete",
                status="queued",
                stage="validating",
                progress_percent=0,
                stage_message="Document deletion accepted and queued.",
                attempt=0,
                max_attempts=3,
            )
        )
        return AcceptedDeletion(job_id, document_id, "queued")
