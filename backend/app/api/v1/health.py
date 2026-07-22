from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session, get_request_id
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.schemas.common import ComponentCheck
from app.schemas.health import LivenessResponse, ReadinessChecks, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse, operation_id="getLiveness")
def get_liveness(request_id: Annotated[str, Depends(get_request_id)]) -> LivenessResponse:
    return LivenessResponse(status="ok", request_id=request_id)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    operation_id="getReadiness",
    responses={503: {"model": ReadinessResponse}},
)
def get_readiness(
    request: Request,
    response: Response,
    request_id: Annotated[str, Depends(get_request_id)],
    session: Annotated[Session, Depends(get_database_session)],
) -> ReadinessResponse:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(RuntimeReadiness, request.app.state.readiness)
    try:
        session.execute(text("SELECT 1"))
        database_ready = runtime.database_ready
        database_detail = "SQLite connection and migrations are ready."
    except SQLAlchemyError:
        database_ready = False
        database_detail = "SQLite is unavailable."

    index_ready = runtime.index_ready and runtime.index_consistent
    retrieval_ready = (
        database_ready and index_ready and runtime.embedding_ready and runtime.worker_ready
    )
    generation_ready = settings.generation_configuration_ready
    checks = ReadinessChecks(
        database=ComponentCheck(ready=database_ready, detail=database_detail),
        index=ComponentCheck(
            ready=index_ready,
            detail=runtime.index_diagnostic,
        ),
        embedding=ComponentCheck(
            ready=runtime.embedding_ready,
            detail=(
                "The configured embedding model is loaded."
                if runtime.embedding_ready
                else "The embedding model is not loaded."
            ),
        ),
        worker=ComponentCheck(
            ready=runtime.worker_ready,
            detail=(
                "The durable worker is accepting jobs."
                if runtime.worker_ready
                else "The durable worker is not started."
            ),
        ),
        generation=ComponentCheck(
            ready=generation_ready,
            detail=(
                "Generation configuration is ready."
                if generation_ready
                else "Generation is disabled or not configured."
            ),
        ),
    )
    if not retrieval_ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ready" if retrieval_ready else "not_ready",
        retrieval_ready=retrieval_ready,
        generation_ready=generation_ready,
        checks=checks,
        request_id=request_id,
    )
