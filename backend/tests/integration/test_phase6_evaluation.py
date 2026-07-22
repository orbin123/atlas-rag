from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from phase3_support import CountingEncoderFactory, DeterministicEncoder, phase3_settings
from sqlalchemy import select

from app.db.models import EvaluationResult, EvaluationRun, IndexState, IngestionJob
from app.main import create_app


class ScriptedProvider:
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: Any) -> str:
        self.calls.append(list(messages))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        return None


def _app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _wait_for_ingestion(client: TestClient, job_id: str, timeout: float = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/ingestion-jobs/{job_id}").json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return cast(dict[str, Any], payload)
        time.sleep(0.02)
    raise AssertionError("Ingestion job did not finish.")


def _wait_for_run(client: TestClient, run_id: str, timeout: float = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/evaluation/runs/{run_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Evaluation run did not finish: {last}")


def _upload(client: TestClient, text: str, domain: str = "Knowledge") -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("eval.txt", text.encode(), "text/plain")},
        data={"domain": domain},
    )
    assert response.status_code == 202, response.text
    assert _wait_for_ingestion(client, response.json()["jobId"])["status"] == "succeeded"


def _seed_gold(client: TestClient, cases: list[dict[str, Any]]) -> str:
    run_id = "86000000-0000-0000-0000-000000000001"
    now = datetime.now(UTC)
    with _app(client).state.session_factory.begin() as session:
        run = EvaluationRun(
            id=run_id,
            mode="retrieval",
            dataset_version="atlas-gold-fixture-v1",
            dataset_hash="f" * 64,
            configuration={"imported": True, "fixture": True},
            status="succeeded",
            progress_percent=100,
            total_questions=len(cases),
            evaluated_questions=len(cases),
            summary_metrics={},
            created_at=now,
            started_at=now,
            completed_at=now,
        )
        session.add(run)
        for case in cases:
            session.add(EvaluationResult(run_id=run_id, **case))
    return run_id


def _retrieval_cases(exact_question: str) -> list[dict[str, Any]]:
    return [
        {
            "evaluation_id": "a_answerable",
            "domain": "Knowledge",
            "question": exact_question,
            "answerable": True,
            "expected_document_name": "eval.txt",
            "expected_page_number": 1,
        },
        {
            "evaluation_id": "b_missing",
            "domain": "Knowledge",
            "question": "A missing source question with unrelated terms.",
            "answerable": True,
            "expected_document_name": "missing.txt",
            "expected_page_number": 1,
        },
        {
            "evaluation_id": "c_unsupported",
            "domain": "Unsupported",
            "question": "Fictional submarine pastry standings.",
            "answerable": False,
        },
        {
            "evaluation_id": "d_false_positive",
            "domain": "Unsupported",
            "question": exact_question,
            "answerable": False,
        },
    ]


@pytest.mark.integration
def test_retrieval_run_persists_metrics_domains_failures_and_latest(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    encoder = DeterministicEncoder(settings.embedding_dimension)
    exact = "Exact evaluation evidence."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            start_worker=True,
        )
    ) as client:
        _upload(client, exact)
        source_run_id = _seed_gold(client, _retrieval_cases(exact))
        response = client.post(
            "/api/v1/evaluation/runs",
            json={"mode": "retrieval", "maximumQuestions": 4},
        )
        assert response.status_code == 202, response.text
        accepted = response.json()
        assert accepted["statusUrl"].endswith(accepted["runId"])
        run = _wait_for_run(client, accepted["runId"])

        assert run["status"] == "succeeded"
        assert run["evaluatedQuestions"] == 4
        assert run["datasetHash"] == "f" * 64
        assert run["metrics"]["recallAt1"] == 0.5
        assert run["metrics"]["recallAt10"] == 0.5
        assert run["metrics"]["mrr"] == 0.5
        assert run["metrics"]["fallbackAccuracy"] == 0.5
        assert run["metrics"]["citationRate"] is None
        assert run["metrics"]["answerCorrectness"] is None
        assert run["metrics"]["groundedness"] is None
        assert run["metrics"]["meanRetrievalLatencyMs"] >= 0

        listing = client.get("/api/v1/evaluation/runs?pageSize=2").json()
        assert listing["total"] == 2
        assert listing["items"][0]["id"] == accepted["runId"]
        _upload(client, "Machine learning source material.", domain="Machine Learning")
        domains = client.get(
            f"/api/v1/evaluation/runs/{accepted['runId']}/domains"
        ).json()
        assert {row["domain"]: (row["documentCount"], row["questionCount"]) for row in domains} == {
            "Knowledge": (1, 2),
            "Machine Learning": (1, 0),
        }
        failures = client.get(
            f"/api/v1/evaluation/runs/{accepted['runId']}/failures?pageSize=10"
        ).json()
        assert {(item["evaluationId"], item["category"]) for item in failures["items"]} == {
            ("b_missing", "Expected Source Missing"),
            ("d_false_positive", "Incorrect Fallback"),
        }
        filtered = client.get(
            f"/api/v1/evaluation/runs/{accepted['runId']}/failures",
            params={"category": "Incorrect Fallback"},
        ).json()
        assert filtered["total"] == 1
        latest = client.get("/api/v1/evaluation/latest").json()
        assert latest["run"]["id"] == accepted["runId"]
        assert len(latest["domains"]) == 2
        assert len(latest["failures"]) == 2

        with _app(client).state.session_factory() as session:
            persisted = session.get_one(EvaluationRun, accepted["runId"])
            assert persisted.configuration["sourceRunId"] == source_run_id
            assert persisted.configuration["retrievalTopK"] == 10
            results = session.scalars(
                select(EvaluationResult).where(EvaluationResult.run_id == accepted["runId"])
            ).all()
            assert len(results) == 4
            assert all(row.answer_correctness is None for row in results)
            assert (
                _app(client).state.ingestion_worker.retrieval
                is _app(client).state.retrieval_service
            )


@pytest.mark.integration
def test_upload_questions_become_evaluation_cases_after_indexing(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            start_worker=True,
        )
    ) as client:
        _seed_gold(client, _retrieval_cases("Base evaluation evidence."))
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("ml.txt", b"Machine learning evaluation evidence.", "text/plain")},
            data={
                "domain": "Machine Learning",
                "evaluationQuestions": (
                    '["What is the machine learning evidence?",'
                    ' "Which domain is described?",'
                    ' "What kind of evaluation is mentioned?"]'
                ),
            },
        )
        assert response.status_code == 202, response.text
        assert _wait_for_ingestion(client, response.json()["jobId"])["status"] == "succeeded"

        accepted = client.post("/api/v1/evaluation/runs", json={"mode": "retrieval"})
        assert accepted.status_code == 202, accepted.text
        run = _wait_for_run(client, accepted.json()["runId"])
        assert run["totalQuestions"] == 7
        domains = client.get(f"/api/v1/evaluation/runs/{run['id']}/domains").json()
        machine_learning = next(row for row in domains if row["domain"] == "Machine Learning")
        assert machine_learning["documentCount"] == 1
        assert machine_learning["questionCount"] == 3


@pytest.mark.integration
def test_generation_evaluation_is_explicit_bounded_and_citation_aware(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    settings.generation_enabled = True
    settings.generation_model = "local-evaluation-model"
    settings.generation_base_url = "http://127.0.0.1:11434/v1"
    encoder = DeterministicEncoder(settings.embedding_dimension)
    provider = ScriptedProvider(["The fixture is supported [S1]."])
    exact = "Exact bounded generation evidence."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            generation_provider_factory=lambda _: provider,
            start_worker=True,
        )
    ) as client:
        _upload(client, exact)
        _seed_gold(client, _retrieval_cases(exact))

        unbounded = client.post("/api/v1/evaluation/runs", json={"mode": "generation"})
        assert unbounded.status_code == 422
        assert unbounded.json()["error"]["code"] == "VALIDATION_ERROR"
        too_large = client.post(
            "/api/v1/evaluation/runs",
            json={"mode": "generation", "maximumQuestions": 11},
        )
        assert too_large.status_code == 422

        response = client.post(
            "/api/v1/evaluation/runs",
            json={"mode": "generation", "maximumQuestions": 1},
        )
        assert response.status_code == 202
        run = _wait_for_run(client, response.json()["runId"])
        assert run["status"] == "succeeded"
        assert run["totalQuestions"] == 1
        assert run["metrics"]["citationRate"] == 1.0
        assert run["metrics"]["fallbackAccuracy"] == 1.0
        assert len(provider.calls) == 1
        with _app(client).state.session_factory() as session:
            result = session.scalar(
                select(EvaluationResult).where(EvaluationResult.run_id == run["id"])
            )
            assert result is not None
            assert result.generated_answer == "The fixture is supported [S1]."
            assert result.citation_valid is True

        provider.outcomes.extend(["No citation.", "Still no citation."])
        invalid_response = client.post(
            "/api/v1/evaluation/runs",
            json={"mode": "generation", "maximumQuestions": 1},
        )
        invalid_run = _wait_for_run(client, invalid_response.json()["runId"])
        assert invalid_run["status"] == "succeeded"
        assert invalid_run["metrics"]["citationRate"] == 0.0
        failures = client.get(
            f"/api/v1/evaluation/runs/{invalid_run['id']}/failures"
        ).json()
        assert failures["items"][0]["category"] == "Invalid Citation"


@pytest.mark.integration
def test_generation_mode_unavailable_is_not_queued(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    exact = "Generation provider availability fixture."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            start_worker=True,
        )
    ) as client:
        _upload(client, exact)
        _seed_gold(client, _retrieval_cases(exact))
        response = client.post(
            "/api/v1/evaluation/runs",
            json={"mode": "generation", "maximumQuestions": 1},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "EVALUATION_MODE_UNAVAILABLE"


@pytest.mark.integration
def test_interrupted_evaluation_job_resumes_after_restart(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    encoder = DeterministicEncoder(settings.embedding_dimension)
    exact = "Restart-safe evaluation evidence."
    factory = CountingEncoderFactory(encoder)
    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        _upload(client, exact)
        source_id = _seed_gold(client, _retrieval_cases(exact)[:1])
        session_factory = _app(client).state.session_factory
        with session_factory() as session:
            index_version = session.get_one(IndexState, 1).index_version

    run_id = "87000000-0000-0000-0000-000000000001"
    job_id = "87000000-0000-0000-0000-000000000002"
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        session.add(
            EvaluationRun(
                id=run_id,
                job_id=job_id,
                mode="retrieval",
                dataset_version="atlas-gold-fixture-v1",
                dataset_hash="f" * 64,
                configuration={
                    "sourceRunId": source_id,
                    "maximumQuestions": 1,
                    "retrievalTopK": 10,
                },
                index_version=index_version,
                status="running",
                progress_percent=20,
                total_questions=1,
                evaluated_questions=0,
                created_at=now,
                started_at=now,
            )
        )
        session.add(
            IngestionJob(
                id=job_id,
                kind="evaluation",
                status="running",
                stage="evaluating",
                progress_percent=20,
                stage_message="Interrupted fixture.",
                attempt=1,
                max_attempts=3,
                started_at=now,
                heartbeat_at=now,
            )
        )

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as restarted:
        run = _wait_for_run(restarted, run_id)
        assert run["status"] == "succeeded"
        assert run["evaluatedQuestions"] == 1
        job = restarted.get(f"/api/v1/ingestion-jobs/{job_id}").json()
        assert job["status"] == "succeeded"
        assert job["attempt"] == 2
