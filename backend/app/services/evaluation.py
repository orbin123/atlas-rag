from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.ids import new_uuid
from app.db.base import utc_now
from app.db.models import (
    Document,
    EvaluationResult,
    EvaluationRun,
    IndexState,
    IngestionJob,
    UploadedEvaluationCase,
)
from app.services.chat import INSUFFICIENT_CONTEXT_ANSWER
from app.services.generation import GenerationInvalidResponseError, GenerationService
from app.services.prompting import build_grounded_messages
from app.services.retrieval import RetrievalService, RetrievedSource

EVALUATION_K_VALUES = (1, 3, 5, 10)


class EvaluationDatasetMissingError(RuntimeError):
    pass


class EvaluationExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class GoldQuestion:
    evaluation_id: str
    domain: str
    question: str
    answerable: bool
    expected_document_name: str | None
    expected_page_number: int | None


@dataclass(frozen=True, slots=True)
class QueuedEvaluation:
    run_id: str
    job_id: str


def canonical_gold_run(session: Session) -> EvaluationRun:
    runs = session.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.status == "succeeded")
        .order_by(EvaluationRun.created_at, EvaluationRun.id)
    ).all()
    for run in runs:
        if bool(run.configuration.get("imported")):
            count = session.scalar(
                select(EvaluationResult.id)
                .where(EvaluationResult.run_id == run.id)
                .limit(1)
            )
            if count is not None:
                return run
    raise EvaluationDatasetMissingError("No imported, versioned gold question set is available.")


def load_gold_questions(
    session: Session, source_run_id: str, *, maximum_questions: int | None = None
) -> tuple[GoldQuestion, ...]:
    statement = (
        select(EvaluationResult)
        .where(EvaluationResult.run_id == source_run_id)
        .order_by(EvaluationResult.evaluation_id)
    )
    rows = session.scalars(statement).all()
    if not rows:
        raise EvaluationDatasetMissingError("The versioned gold question set is empty.")
    cases = [
        GoldQuestion(
            evaluation_id=row.evaluation_id,
            domain=row.domain,
            question=row.question,
            answerable=row.answerable,
            expected_document_name=row.expected_document_name,
            expected_page_number=row.expected_page_number,
        )
        for row in rows
    ]
    uploaded = session.execute(
        select(UploadedEvaluationCase, Document)
        .join(Document, Document.id == UploadedEvaluationCase.document_id)
        .where(Document.status == "indexed")
        .order_by(UploadedEvaluationCase.created_at, UploadedEvaluationCase.id)
    ).all()
    cases.extend(
        GoldQuestion(
            evaluation_id=f"upload-{case.id}",
            domain=document.domain,
            question=case.question,
            answerable=True,
            expected_document_name=document.original_file_name,
            expected_page_number=None,
        )
        for case, document in uploaded
    )
    return tuple(cases[:maximum_questions] if maximum_questions is not None else cases)


def queue_evaluation_run(
    session: Session,
    *,
    settings: Settings,
    state: IndexState,
    mode: str,
    maximum_questions: int | None,
) -> QueuedEvaluation:
    source = canonical_gold_run(session)
    questions = load_gold_questions(
        session, source.id, maximum_questions=maximum_questions
    )
    run_id = new_uuid()
    job_id = new_uuid()
    retrieval_top_k = max(EVALUATION_K_VALUES)
    run = EvaluationRun(
        id=run_id,
        job_id=job_id,
        mode=mode,
        dataset_version=source.dataset_version,
        dataset_hash=source.dataset_hash,
        configuration={
            "sourceRunId": source.id,
            "maximumQuestions": maximum_questions,
            "kValues": list(EVALUATION_K_VALUES),
            "retrievalTopK": retrieval_top_k,
            "minimumContextScore": settings.minimum_context_score,
            "duplicateSimilarityThreshold": settings.duplicate_similarity_threshold,
            "embeddingModel": settings.embedding_model,
            "embeddingRevision": settings.embedding_revision,
            "embeddingDimension": settings.embedding_dimension,
            "generationModel": settings.generation_model if mode == "generation" else None,
        },
        index_version=state.index_version,
        status="queued",
        progress_percent=0,
        total_questions=len(questions),
        evaluated_questions=0,
    )
    session.add(run)
    session.add(
        IngestionJob(
            id=job_id,
            kind="evaluation",
            status="queued",
            stage="evaluating",
            progress_percent=0,
            stage_message="Evaluation run is queued.",
            attempt=0,
            max_attempts=3,
            result={"runId": run_id},
        )
    )
    session.commit()
    return QueuedEvaluation(run_id=run_id, job_id=job_id)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def metric_summary(rows: Sequence[EvaluationResult]) -> dict[str, float | int | None]:
    answerable = [row for row in rows if row.answerable]
    citation_values = [
        float(row.citation_valid) for row in rows if row.citation_valid is not None
    ]
    fallback_values = [
        float(row.fallback_correct) for row in rows if row.fallback_correct is not None
    ]
    return {
        "answerableQuestions": len(answerable),
        "unsupportedQuestions": len(rows) - len(answerable),
        "recallAt1": _mean([float(bool(row.recall_at_1)) for row in answerable]),
        "recallAt3": _mean([float(bool(row.recall_at_3)) for row in answerable]),
        "recallAt5": _mean([float(bool(row.recall_at_5)) for row in answerable]),
        "recallAt10": _mean([float(bool(row.recall_at_10)) for row in answerable]),
        "mrr": _mean([float(row.mrr_contribution or 0.0) for row in answerable]),
        "meanRetrievalLatencyMs": _mean(
            [
                float(row.retrieval_latency_ms)
                for row in rows
                if row.retrieval_latency_ms is not None
            ]
        ),
        "fallbackAccuracy": _mean(fallback_values),
        "citationRate": _mean(citation_values),
        "answerCorrectness": _mean(
            [float(row.answer_correctness) for row in rows if row.answer_correctness is not None]
        ),
        "groundedness": _mean(
            [float(row.groundedness) for row in rows if row.groundedness is not None]
        ),
    }


def first_relevant_rank(
    sources: Sequence[RetrievedSource],
    expected_document_name: str | None,
    expected_page_number: int | None,
) -> int | None:
    if expected_document_name is None:
        return None
    for source in sources:
        if source.document_name != expected_document_name:
            continue
        if expected_page_number is None or source.page_number == expected_page_number:
            return source.rank
    return None


def _manual_review_failed(value: float | None) -> bool:
    if value is None:
        return False
    return value < 0.5 if value <= 1 else value < 3


def failure_for_result(
    *,
    answerable: bool,
    source_count: int,
    first_rank: int | None,
    default_top_k: int,
    citation_valid: bool | None,
    fallback_correct: bool | None,
    answer_correctness: float | None = None,
    groundedness: float | None = None,
) -> tuple[str | None, str | None]:
    if answerable and source_count == 0:
        return "No Context Retrieved", "No source was returned for an answerable question."
    if answerable and first_rank is None:
        return "Expected Source Missing", "The expected source was absent from the top ten."
    if answerable and first_rank is not None and first_rank > default_top_k:
        return "Incorrect Rank", f"The first expected source ranked {first_rank}."
    if citation_valid is False:
        return "Invalid Citation", "Generation did not return a valid supplied source label."
    if fallback_correct is False:
        return "Incorrect Fallback", "The context gate made the wrong answerability decision."
    if _manual_review_failed(answer_correctness) or _manual_review_failed(groundedness):
        return "Manual Review Failure", "A recorded manual answer-quality rating failed."
    return None, None


def _save_result(
    session: Session,
    *,
    run_id: str,
    case: GoldQuestion,
    sources: tuple[RetrievedSource, ...],
    latency_ms: float,
    settings: Settings,
    generated_answer: str | None,
    citation_valid: bool | None,
) -> None:
    rank = first_relevant_rank(
        sources, case.expected_document_name, case.expected_page_number
    )
    top = sources[0] if sources else None
    insufficient = top is None or top.similarity_score < settings.minimum_context_score
    fallback_correct = insufficient == (not case.answerable)
    category, summary = failure_for_result(
        answerable=case.answerable,
        source_count=len(sources),
        first_rank=rank,
        default_top_k=settings.default_top_k,
        citation_valid=citation_valid,
        fallback_correct=fallback_correct,
    )
    session.add(
        EvaluationResult(
            run_id=run_id,
            evaluation_id=case.evaluation_id,
            domain=case.domain,
            question=case.question,
            answerable=case.answerable,
            expected_document_name=case.expected_document_name,
            expected_page_number=case.expected_page_number,
            first_relevant_rank=rank,
            recall_at_1=(rank is not None and rank <= 1) if case.answerable else None,
            recall_at_3=(rank is not None and rank <= 3) if case.answerable else None,
            recall_at_5=(rank is not None and rank <= 5) if case.answerable else None,
            recall_at_10=(rank is not None and rank <= 10) if case.answerable else None,
            mrr_contribution=(1.0 / rank if rank is not None else 0.0)
            if case.answerable
            else None,
            top_score=top.similarity_score if top else None,
            top_document_name=top.document_name if top else None,
            top_page_number=top.page_number if top else None,
            retrieval_latency_ms=latency_ms,
            generated_answer=generated_answer,
            citation_valid=citation_valid,
            fallback_correct=fallback_correct,
            failure_category=category,
            failure_summary=summary,
        )
    )


def _refresh_run_metrics(session: Session, run_id: str, total: int) -> None:
    run = session.get_one(EvaluationRun, run_id)
    rows = session.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.run_id == run_id)
        .order_by(EvaluationResult.evaluation_id)
    ).all()
    run.evaluated_questions = len(rows)
    run.progress_percent = min(99, int(len(rows) * 100 / total))
    run.summary_metrics = metric_summary(rows) if rows else None


async def execute_evaluation_run(
    *,
    run_id: str,
    settings: Settings,
    session_factory: sessionmaker[Session],
    retrieval: RetrievalService,
    generation: GenerationService,
    index: Any,
    progress: Callable[[int, int], None],
) -> None:
    with session_factory() as session:
        run = session.get(EvaluationRun, run_id)
        if run is None:
            raise EvaluationExecutionError(
                "EVALUATION_RUN_NOT_FOUND", "The queued evaluation run is missing.", retryable=False
            )
        source_run_id = str(run.configuration.get("sourceRunId") or "")
        maximum = run.configuration.get("maximumQuestions")
        cases = load_gold_questions(
            session,
            source_run_id,
            maximum_questions=int(maximum) if maximum is not None else None,
        )
        mode = run.mode
        existing = set(
            session.scalars(
                select(EvaluationResult.evaluation_id).where(EvaluationResult.run_id == run_id)
            ).all()
        )
    retrieval_top_k = max(EVALUATION_K_VALUES)
    if retrieval_top_k > settings.max_top_k:
        raise EvaluationExecutionError(
            "EVALUATION_CONFIGURATION_INVALID",
            "Evaluation requires ATLAS_MAX_TOP_K to be at least 10.",
            retryable=False,
        )

    for case in cases:
        if case.evaluation_id in existing:
            continue
        with session_factory() as retrieval_session:
            retrieved = await retrieval.retrieve(
                session=retrieval_session,
                index=index,
                question=case.question,
                top_k=retrieval_top_k,
            )
        top = retrieved.sources[0] if retrieved.sources else None
        insufficient = top is None or top.similarity_score < settings.minimum_context_score
        generated_answer: str | None = None
        citation_valid: bool | None = None
        if mode == "generation":
            if insufficient:
                generated_answer = INSUFFICIENT_CONTEXT_ANSWER
            else:
                messages, prompt_sources = build_grounded_messages(
                    case.question,
                    retrieved.sources,
                    token_budget=settings.generation_context_max_tokens,
                )
                try:
                    generated_answer, _ = await generation.generate_validated(
                        messages,
                        allowed_labels=[source.label for source in prompt_sources],
                    )
                    citation_valid = True
                except GenerationInvalidResponseError:
                    citation_valid = False
        with session_factory.begin() as session:
            _save_result(
                session,
                run_id=run_id,
                case=case,
                sources=retrieved.sources,
                latency_ms=retrieved.latency_ms,
                settings=settings,
                generated_answer=generated_answer,
                citation_valid=citation_valid,
            )
            session.flush()
            _refresh_run_metrics(session, run_id, len(cases))
        progress(len(existing) + 1, len(cases))
        existing.add(case.evaluation_id)

    with session_factory.begin() as session:
        run = session.get_one(EvaluationRun, run_id)
        rows = session.scalars(
            select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        ).all()
        run.status = "succeeded"
        run.progress_percent = 100
        run.evaluated_questions = len(rows)
        run.summary_metrics = metric_summary(rows)
        run.completed_at = utc_now()
