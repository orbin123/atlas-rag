from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.api.errors import APIError
from app.db.models import IngestionJob
from app.schemas.ingestion import IngestionJobError, IngestionJobResponse

router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion-jobs"])


@router.get("/{jobId}", response_model=IngestionJobResponse, operation_id="getIngestionJob")
def get_ingestion_job(
    job_id: Annotated[str, Path(alias="jobId")],
    session: Annotated[Session, Depends(get_database_session)],
) -> IngestionJobResponse:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise APIError(
            code="JOB_NOT_FOUND",
            message="The requested ingestion job was not found.",
            status_code=404,
            details={"jobId": job_id},
        )
    return IngestionJobResponse(
        id=job.id,
        document_id=job.document_id,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        progress_percent=job.progress_percent,
        stage_message=job.stage_message,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        result=job.result,
        error=(
            IngestionJobError(code=job.error_code, message=job.error_message)
            if job.error_code and job.error_message
            else None
        ),
        created_at=job.created_at,
        started_at=job.started_at,
        heartbeat_at=job.heartbeat_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )
