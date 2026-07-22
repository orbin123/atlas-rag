from __future__ import annotations

import math
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi import Query as QueryParameter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.api.errors import APIError
from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.db.models import Document, EvaluationResult, EvaluationRun, IndexState
from app.schemas.common import PaginatedResponse
from app.schemas.evaluation import (
    EvaluationDomainMetric,
    EvaluationFailure,
    EvaluationLatestResponse,
    EvaluationMetrics,
    EvaluationRunAcceptedResponse,
    EvaluationRunRequest,
    EvaluationRunSummary,
)
from app.services.evaluation import (
    EvaluationDatasetMissingError,
    metric_summary,
    queue_evaluation_run,
)
from app.services.generation import GenerationService

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _metrics(values: dict[str, Any] | None) -> EvaluationMetrics:
    values = values or {}
    return EvaluationMetrics(
        recall_at_1=values.get("recallAt1"),
        recall_at_3=values.get("recallAt3"),
        recall_at_5=values.get("recallAt5"),
        recall_at_10=values.get("recallAt10"),
        mrr=values.get("mrr"),
        mean_retrieval_latency_ms=values.get("meanRetrievalLatencyMs"),
        fallback_accuracy=values.get("fallbackAccuracy"),
        citation_rate=values.get("citationRate"),
        answer_correctness=values.get("answerCorrectness"),
        groundedness=values.get("groundedness"),
    )


def _run_summary(run: EvaluationRun) -> EvaluationRunSummary:
    return EvaluationRunSummary(
        id=run.id,
        mode=run.mode,
        status=run.status,
        progress_percent=run.progress_percent,
        dataset_version=run.dataset_version,
        dataset_hash=run.dataset_hash,
        index_version=run.index_version,
        evaluated_questions=run.evaluated_questions,
        total_questions=run.total_questions,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        metrics=_metrics(run.summary_metrics),
    )


def _get_run(session: Session, run_id: str) -> EvaluationRun:
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise APIError(
            code="EVALUATION_RUN_NOT_FOUND",
            message="The requested evaluation run was not found.",
            status_code=404,
            details={"runId": run_id},
        )
    return run


def _domain_metrics(session: Session, run_id: str) -> list[EvaluationDomainMetric]:
    # "Unsupported" is the label used by the versioned gold dataset for
    # intentionally unanswerable questions.  It is an evaluation cohort, not a
    # corpus domain, so it must not be presented as a document domain.
    evaluated_domains = session.scalars(
        select(EvaluationResult.domain)
        .where(EvaluationResult.run_id == run_id)
        .where(EvaluationResult.answerable.is_(True))
        .distinct()
    ).all()
    document_counts = dict(
        session.execute(
            select(Document.domain, func.count())
            .where(Document.status == "indexed")
            .group_by(Document.domain)
        ).all()
    )
    domains = sorted(set(evaluated_domains) | set(document_counts))
    response: list[EvaluationDomainMetric] = []
    for domain in domains:
        rows = session.scalars(
            select(EvaluationResult).where(
                EvaluationResult.run_id == run_id,
                EvaluationResult.domain == domain,
                EvaluationResult.answerable.is_(True),
            )
        ).all()
        values = metric_summary(rows)
        response.append(
            EvaluationDomainMetric(
                domain=domain,
                document_count=int(document_counts.get(domain, 0)),
                question_count=len(rows),
                recall_at_1=cast(float | None, values["recallAt1"]),
                recall_at_3=cast(float | None, values["recallAt3"]),
                recall_at_5=cast(float | None, values["recallAt5"]),
                recall_at_10=cast(float | None, values["recallAt10"]),
                mrr=cast(float | None, values["mrr"]),
                mean_retrieval_latency_ms=cast(
                    float | None, values["meanRetrievalLatencyMs"]
                ),
                fallback_accuracy=cast(float | None, values["fallbackAccuracy"]),
                citation_rate=cast(float | None, values["citationRate"]),
                answer_correctness=cast(float | None, values["answerCorrectness"]),
                groundedness=cast(float | None, values["groundedness"]),
            )
        )
    return response


def _failure(row: EvaluationResult) -> EvaluationFailure:
    return EvaluationFailure(
        id=row.id,
        evaluation_id=row.evaluation_id,
        question=row.question,
        domain=row.domain,
        category=row.failure_category or "Uncategorized",
        expected_document_name=row.expected_document_name,
        expected_page_number=row.expected_page_number,
        retrieved_document_name=row.top_document_name,
        retrieved_page_number=row.top_page_number,
        first_relevant_rank=row.first_relevant_rank,
        top_score=row.top_score,
        summary=row.failure_summary or "The evaluation record requires review.",
    )


@router.post(
    "/runs",
    response_model=EvaluationRunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createEvaluationRun",
)
def create_evaluation_run(
    body: EvaluationRunRequest,
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> EvaluationRunAcceptedResponse:
    readiness = cast(RuntimeReadiness, request.app.state.readiness)
    settings = cast(Settings, request.app.state.settings)
    if not readiness.index_ready or not readiness.index_consistent:
        raise APIError(
            code="INDEX_NOT_READY",
            message="No verified active retrieval index is available.",
            status_code=503,
        )
    if not readiness.worker_ready or not hasattr(request.app.state, "ingestion_worker"):
        raise APIError(
            code="WORKER_NOT_READY",
            message="The durable local worker is not ready.",
            status_code=503,
        )
    generation = cast(GenerationService, request.app.state.generation_service)
    if body.mode == "generation" and not generation.ready:
        raise APIError(
            code="EVALUATION_MODE_UNAVAILABLE",
            message="Generation evaluation is unavailable until a provider is configured.",
            status_code=503,
        )
    if body.mode == "generation" and body.maximum_questions is None:
        raise APIError(
            code="VALIDATION_ERROR",
            message="Generation evaluation requires a bounded maximumQuestions value.",
            status_code=422,
        )
    if (
        body.mode == "generation"
        and body.maximum_questions is not None
        and body.maximum_questions > settings.evaluation_generation_max_questions
    ):
        raise APIError(
            code="VALIDATION_ERROR",
            message=(
                "maximumQuestions exceeds the configured generation-evaluation safety bound."
            ),
            status_code=422,
            details={"maximum": settings.evaluation_generation_max_questions},
        )
    state = session.get(IndexState, 1)
    if state is None:
        raise APIError(code="INDEX_NOT_READY", message="No active index exists.", status_code=503)
    try:
        queued = queue_evaluation_run(
            session,
            settings=settings,
            state=state,
            mode=body.mode,
            maximum_questions=body.maximum_questions,
        )
    except EvaluationDatasetMissingError as exc:
        raise APIError(
            code="EVALUATION_DATASET_MISSING", message=str(exc), status_code=503
        ) from exc
    request.app.state.ingestion_worker.kick()
    return EvaluationRunAcceptedResponse(
        run_id=queued.run_id,
        job_id=queued.job_id,
        status="queued",
        status_url=f"/api/v1/evaluation/runs/{queued.run_id}",
    )


@router.get(
    "/runs",
    response_model=PaginatedResponse[EvaluationRunSummary],
    operation_id="listEvaluationRuns",
)
def list_evaluation_runs(
    session: Annotated[Session, Depends(get_database_session)],
    page: Annotated[int, QueryParameter(ge=1)] = 1,
    page_size: Annotated[int, QueryParameter(alias="pageSize", ge=1, le=100)] = 25,
) -> PaginatedResponse[EvaluationRunSummary]:
    total = int(session.scalar(select(func.count()).select_from(EvaluationRun)) or 0)
    rows = session.scalars(
        select(EvaluationRun)
        .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PaginatedResponse(
        items=[_run_summary(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/runs/{runId}", response_model=EvaluationRunSummary, operation_id="getEvaluationRun"
)
def get_evaluation_run(
    run_id: Annotated[str, Path(alias="runId")],
    session: Annotated[Session, Depends(get_database_session)],
) -> EvaluationRunSummary:
    return _run_summary(_get_run(session, run_id))


@router.get(
    "/runs/{runId}/domains",
    response_model=list[EvaluationDomainMetric],
    operation_id="listEvaluationDomains",
)
def list_evaluation_domains(
    run_id: Annotated[str, Path(alias="runId")],
    session: Annotated[Session, Depends(get_database_session)],
) -> list[EvaluationDomainMetric]:
    _get_run(session, run_id)
    return _domain_metrics(session, run_id)


@router.get(
    "/runs/{runId}/failures",
    response_model=PaginatedResponse[EvaluationFailure],
    operation_id="listEvaluationFailures",
)
def list_evaluation_failures(
    run_id: Annotated[str, Path(alias="runId")],
    session: Annotated[Session, Depends(get_database_session)],
    page: Annotated[int, QueryParameter(ge=1)] = 1,
    page_size: Annotated[int, QueryParameter(alias="pageSize", ge=1, le=100)] = 25,
    category: Annotated[str | None, QueryParameter(min_length=1, max_length=64)] = None,
    domain: Annotated[str | None, QueryParameter(min_length=1, max_length=255)] = None,
) -> PaginatedResponse[EvaluationFailure]:
    _get_run(session, run_id)
    filters = [
        EvaluationResult.run_id == run_id,
        EvaluationResult.failure_category.is_not(None),
    ]
    if category is not None:
        filters.append(EvaluationResult.failure_category == category)
    if domain is not None:
        filters.append(EvaluationResult.domain == domain)
    total = int(
        session.scalar(select(func.count()).select_from(EvaluationResult).where(*filters)) or 0
    )
    rows = session.scalars(
        select(EvaluationResult)
        .where(*filters)
        .order_by(EvaluationResult.evaluation_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PaginatedResponse(
        items=[_failure(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/latest", response_model=EvaluationLatestResponse, operation_id="getLatestEvaluation"
)
def get_latest_evaluation(
    session: Annotated[Session, Depends(get_database_session)],
) -> EvaluationLatestResponse:
    run = session.scalar(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
    )
    if run is None:
        raise APIError(
            code="EVALUATION_DATASET_MISSING",
            message="No evaluation run is available.",
            status_code=503,
        )
    failures = session.scalars(
        select(EvaluationResult)
        .where(
            EvaluationResult.run_id == run.id,
            EvaluationResult.failure_category.is_not(None),
        )
        .order_by(EvaluationResult.evaluation_id)
        .limit(100)
    ).all()
    return EvaluationLatestResponse(
        run=_run_summary(run),
        domains=_domain_metrics(session, run.id),
        failures=[_failure(row) for row in failures],
    )
