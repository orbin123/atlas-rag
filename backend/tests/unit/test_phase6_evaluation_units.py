from __future__ import annotations

import pytest

from app.db.models import EvaluationResult
from app.services.evaluation import failure_for_result, metric_summary


def _row(**overrides: object) -> EvaluationResult:
    values: dict[str, object] = {
        "run_id": "run",
        "evaluation_id": "case",
        "domain": "Domain",
        "question": "Question?",
        "answerable": True,
        "recall_at_1": True,
        "recall_at_3": True,
        "recall_at_5": True,
        "recall_at_10": True,
        "mrr_contribution": 1.0,
        "retrieval_latency_ms": 10.0,
        "fallback_correct": True,
    }
    values.update(overrides)
    return EvaluationResult(**values)


def test_metric_summary_matches_independent_fixture_calculation() -> None:
    rows = [
        _row(evaluation_id="a", citation_valid=True, answer_correctness=4.0),
        _row(
            evaluation_id="b",
            recall_at_1=False,
            recall_at_3=False,
            recall_at_5=True,
            mrr_contribution=0.2,
            retrieval_latency_ms=30.0,
            fallback_correct=False,
            citation_valid=False,
            groundedness=3.0,
        ),
        _row(
            evaluation_id="u",
            answerable=False,
            recall_at_1=None,
            recall_at_3=None,
            recall_at_5=None,
            recall_at_10=None,
            mrr_contribution=None,
            retrieval_latency_ms=20.0,
            fallback_correct=True,
            citation_valid=None,
        ),
    ]

    summary = metric_summary(rows)

    assert summary["answerableQuestions"] == 2
    assert summary["unsupportedQuestions"] == 1
    assert summary["recallAt1"] == 0.5
    assert summary["recallAt3"] == 0.5
    assert summary["recallAt5"] == 1.0
    assert summary["recallAt10"] == 1.0
    assert summary["mrr"] == pytest.approx(0.6)
    assert summary["meanRetrievalLatencyMs"] == 20.0
    assert summary["fallbackAccuracy"] == pytest.approx(2 / 3)
    assert summary["citationRate"] == 0.5
    assert summary["answerCorrectness"] == 4.0
    assert summary["groundedness"] == 3.0


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            {"answerable": True, "source_count": 0, "first_rank": None},
            "No Context Retrieved",
        ),
        (
            {"answerable": True, "source_count": 2, "first_rank": None},
            "Expected Source Missing",
        ),
        (
            {"answerable": True, "source_count": 10, "first_rank": 7},
            "Incorrect Rank",
        ),
        (
            {
                "answerable": False,
                "source_count": 2,
                "first_rank": None,
                "citation_valid": False,
            },
            "Invalid Citation",
        ),
        (
            {
                "answerable": False,
                "source_count": 2,
                "first_rank": None,
                "fallback_correct": False,
            },
            "Incorrect Fallback",
        ),
        (
            {
                "answerable": False,
                "source_count": 2,
                "first_rank": None,
                "answer_correctness": 2.0,
            },
            "Manual Review Failure",
        ),
    ],
)
def test_failure_categories_are_stable(arguments: dict[str, object], expected: str) -> None:
    defaults: dict[str, object] = {
        "answerable": False,
        "source_count": 1,
        "first_rank": None,
        "default_top_k": 5,
        "citation_valid": None,
        "fallback_correct": True,
    }
    defaults.update(arguments)
    category, summary = failure_for_result(**defaults)  # type: ignore[arg-type]
    assert category == expected
    assert summary


def test_missing_manual_metrics_remain_null() -> None:
    summary = metric_summary([_row(answer_correctness=None, groundedness=None)])
    assert summary["answerCorrectness"] is None
    assert summary["groundedness"] is None
