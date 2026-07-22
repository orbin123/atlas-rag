from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import CamelModel


class AcceptedJobResponse(CamelModel):
    job_id: str
    document_id: str
    status: str
    status_url: str


class IngestionJobError(CamelModel):
    code: str
    message: str


class IngestionJobResponse(CamelModel):
    id: str
    document_id: str | None
    kind: str
    status: str
    stage: str | None
    progress_percent: int
    stage_message: str | None
    attempt: int
    max_attempts: int
    result: dict[str, Any] | None
    error: IngestionJobError | None
    created_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
