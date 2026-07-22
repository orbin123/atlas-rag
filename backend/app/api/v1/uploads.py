from __future__ import annotations

import asyncio
import json
from typing import Annotated, cast

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import APIError
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.schemas.ingestion import AcceptedJobResponse
from app.services.uploads import UploadMetadata, accept_staged_upload
from app.storage.files import UploadFileError, stage_upload
from app.workers.runner import IngestionWorker

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=AcceptedJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadDocument",
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    domain: Annotated[str, Form(max_length=255)] = "user-uploaded",
    title: Annotated[str | None, Form(max_length=512)] = None,
    author: Annotated[str | None, Form(max_length=512)] = None,
    source_url: Annotated[str | None, Form(alias="sourceUrl", max_length=2048)] = None,
    license_note: Annotated[str | None, Form(alias="licenseNote", max_length=4000)] = None,
    evaluation_questions: Annotated[
        str | None, Form(alias="evaluationQuestions", max_length=12000)
    ] = None,
) -> AcceptedJobResponse:
    readiness = cast(RuntimeReadiness, request.app.state.readiness)
    if not readiness.worker_ready:
        raise APIError(
            code="WORKER_NOT_READY",
            message="The ingestion worker is not ready to accept uploads.",
            status_code=503,
        )
    settings = cast(Settings, request.app.state.settings)
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    worker = cast(IngestionWorker, request.app.state.ingestion_worker)
    try:
        try:
            parsed_questions = json.loads(evaluation_questions) if evaluation_questions else []
        except json.JSONDecodeError as exc:
            raise UploadFileError(
                "VALIDATION_ERROR", "Evaluation questions must be a JSON array of strings.", 422
            ) from exc
        if not isinstance(parsed_questions, list) or not all(
            isinstance(question, str) for question in parsed_questions
        ):
            raise UploadFileError(
                "VALIDATION_ERROR", "Evaluation questions must be a JSON array of strings.", 422
            )
        staged = await stage_upload(file, settings)
        accepted = await asyncio.to_thread(
            accept_staged_upload,
            staged,
            UploadMetadata(
                domain=domain,
                title=title,
                author=author,
                source_url=source_url,
                license_note=license_note,
                evaluation_questions=tuple(parsed_questions),
            ),
            settings,
            factory,
        )
    except UploadFileError as exc:
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
        status="queued",
        status_url=f"/api/v1/ingestion-jobs/{accepted.job_id}",
    )
