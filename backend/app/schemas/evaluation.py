from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel


class EvaluationRunRequest(CamelModel):
    mode: Literal["retrieval", "generation"] = "retrieval"
    maximum_questions: int | None = Field(default=None, ge=1, le=1000)


class EvaluationRunAcceptedResponse(CamelModel):
    run_id: str
    job_id: str
    status: str
    status_url: str


class EvaluationMetrics(CamelModel):
    recall_at_1: float | None = Field(default=None, alias="recallAt1")
    recall_at_3: float | None = Field(default=None, alias="recallAt3")
    recall_at_5: float | None = Field(default=None, alias="recallAt5")
    recall_at_10: float | None = Field(default=None, alias="recallAt10")
    mrr: float | None = None
    mean_retrieval_latency_ms: float | None = None
    fallback_accuracy: float | None = None
    citation_rate: float | None = None
    answer_correctness: float | None = None
    groundedness: float | None = None


class EvaluationRunSummary(CamelModel):
    id: str
    mode: str
    status: str
    progress_percent: int
    dataset_version: str
    dataset_hash: str
    index_version: str | None
    evaluated_questions: int
    total_questions: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    metrics: EvaluationMetrics


class EvaluationDomainMetric(CamelModel):
    domain: str
    document_count: int
    question_count: int
    recall_at_1: float | None = Field(alias="recallAt1")
    recall_at_3: float | None = Field(alias="recallAt3")
    recall_at_5: float | None = Field(alias="recallAt5")
    recall_at_10: float | None = Field(alias="recallAt10")
    mrr: float | None
    mean_retrieval_latency_ms: float | None
    fallback_accuracy: float | None
    citation_rate: float | None
    answer_correctness: float | None
    groundedness: float | None


class EvaluationFailure(CamelModel):
    id: str
    evaluation_id: str
    question: str
    domain: str
    category: str
    expected_document_name: str | None
    expected_page_number: int | None
    retrieved_document_name: str | None
    retrieved_page_number: int | None
    first_relevant_rank: int | None
    top_score: float | None
    summary: str


class EvaluationLatestResponse(CamelModel):
    run: EvaluationRunSummary
    domains: list[EvaluationDomainMetric]
    failures: list[EvaluationFailure]
