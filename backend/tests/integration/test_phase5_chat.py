from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from phase3_support import CountingEncoderFactory, DeterministicEncoder, phase3_settings
from sqlalchemy import func, select

from app.db.models import EvaluationResult, EvaluationRun, Query, QuerySource
from app.main import create_app


class ScriptedProvider:
    def __init__(self) -> None:
        self.outcomes: list[str | Exception] = []
        self.calls: list[list[dict[str, str]]] = []
        self.closed = False

    async def complete(self, messages: Any) -> str:
        self.calls.append(list(messages))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        self.closed = True


def _app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/ingestion-jobs/{job_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish before timeout: {last}")


def _upload(client: TestClient, name: str, text: str, domain: str = "Knowledge") -> str:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, text.encode(), "text/plain")},
        data={"domain": domain},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert _wait_for_job(client, payload["jobId"])["status"] == "succeeded"
    return str(payload["documentId"])


def _generation_settings(tmp_path: Path) -> Any:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    settings.generation_enabled = True
    settings.generation_model = "local-test-model"
    settings.generation_base_url = "http://127.0.0.1:11434/v1"
    return settings


def test_supported_chat_persists_evidence_suggestions_and_survives_source_deletion(
    tmp_path: Path,
) -> None:
    settings = _generation_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    provider = ScriptedProvider()
    provider.outcomes.append("Atlas uses durable evidence [S1].")
    content = "Atlas retrieval preserves durable evidence for later inspection."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            generation_provider_factory=lambda _: provider,
            start_worker=True,
        )
    ) as client:
        document_id = _upload(client, "durable-evidence.txt", content)
        response = client.post(
            "/api/v1/chat/queries",
            json={"question": content, "topK": 5, "domain": "Knowledge"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["answer"] == "Atlas uses durable evidence [S1]."
        assert payload["insufficientContext"] is False
        assert payload["citations"][0]["label"] == "S1"
        assert payload["sources"][0]["documentId"] == document_id
        assert payload["sources"][0]["similarityScore"] > 0.9999
        assert payload["config"]["indexVersion"]
        query_id = payload["queryId"]

        detail = client.get(f"/api/v1/retrieval/{query_id}")
        assert detail.status_code == 200
        assert detail.json()["sources"] == payload["sources"]
        assert detail.json()["status"] == "completed"

        with _app(client).state.session_factory.begin() as session:
            run = EvaluationRun(
                id="70000000-0000-0000-0000-000000000001",
                mode="retrieval",
                dataset_version="unit-gold-v1",
                dataset_hash="a" * 64,
                configuration={"fixture": True, "imported": True},
                status="succeeded",
                progress_percent=100,
                total_questions=2,
                evaluated_questions=2,
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            session.add(run)
            session.add_all(
                [
                    EvaluationResult(
                        run_id=run.id,
                        evaluation_id="answerable",
                        domain="Knowledge",
                        question="What evidence is durable?",
                        answerable=True,
                        expected_document_name="durable-evidence.txt",
                    ),
                    EvaluationResult(
                        run_id=run.id,
                        evaluation_id="unsupported",
                        domain="Knowledge",
                        question="An unsupported suggestion",
                        answerable=False,
                    ),
                ]
            )
        suggestions = client.get("/api/v1/chat/suggestions?limit=4")
        assert suggestions.status_code == 200
        assert suggestions.json() == [
            {
                "id": "answerable",
                "question": "What evidence is durable?",
                "domain": "Knowledge",
            }
        ]

        unsupported = client.post(
            "/api/v1/chat/queries",
            json={"question": "This unrelated hash should not match the evidence."},
        )
        assert unsupported.status_code == 200
        unsupported_payload = unsupported.json()
        assert unsupported_payload["insufficientContext"] is True
        assert unsupported_payload["answer"].startswith("I don't have enough evidence")
        assert unsupported_payload["citations"] == []
        assert len(provider.calls) == 1

        deletion = client.delete(f"/api/v1/documents/{document_id}")
        assert deletion.status_code == 202
        assert _wait_for_job(client, deletion.json()["jobId"])["status"] == "succeeded"
        persisted = client.get(f"/api/v1/retrieval/{query_id}")
        assert persisted.status_code == 200
        assert persisted.json()["sources"][0]["documentName"] == "durable-evidence.txt"
    assert provider.closed is True


def test_domain_filter_overfetches_and_top_k_is_bounded(tmp_path: Path) -> None:
    settings = _generation_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    provider = ScriptedProvider()
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            generation_provider_factory=lambda _: provider,
            start_worker=True,
        )
    ) as client:
        first = "Exact source content from the excluded domain."
        _upload(client, "excluded.txt", first, "Excluded")
        target_id = _upload(client, "target.txt", "Lower scoring target-domain evidence.", "Target")
        response = client.post(
            "/api/v1/chat/queries",
            json={"question": first, "domain": "Target", "topK": 2},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["insufficientContext"] is True
        assert {source["documentId"] for source in payload["sources"]} == {target_id}
        too_many = client.post(
            "/api/v1/chat/queries",
            json={"question": first, "topK": settings.max_top_k + 1},
        )
        assert too_many.status_code == 422
        assert too_many.json()["error"]["code"] == "VALIDATION_ERROR"


def test_provider_and_citation_failures_are_typed_and_persisted(tmp_path: Path) -> None:
    settings = _generation_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    provider = ScriptedProvider()
    content = "Exact evidence passes the configured context gate."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            generation_provider_factory=lambda _: provider,
            start_worker=True,
        )
    ) as client:
        _upload(client, "provider.txt", content)
        scenarios: list[tuple[list[str | Exception], int, str]] = [
            ([TimeoutError("provider timeout")], 504, "GENERATION_TIMEOUT"),
            ([RuntimeError("provider down")], 503, "GENERATION_PROVIDER_ERROR"),
            (["No citation.", "Still no citation."], 502, "GENERATION_RESPONSE_INVALID"),
        ]
        query_ids: list[str] = []
        for outcomes, status, code in scenarios:
            provider.outcomes.extend(outcomes)
            response = client.post("/api/v1/chat/queries", json={"question": content})
            assert response.status_code == status, response.text
            assert response.json()["error"]["code"] == code
            query_ids.append(response.json()["error"]["details"]["queryId"])

        with _app(client).state.session_factory() as session:
            queries = session.scalars(select(Query).where(Query.id.in_(query_ids))).all()
            assert {query.status for query in queries} == {"generation_failed"}
            assert all(query.citation_valid is False for query in queries)
            assert session.scalar(
                select(func.count())
                .select_from(QuerySource)
                .where(QuerySource.query_id.in_(query_ids))
            ) == len(query_ids)


def test_provider_disabled_is_not_reported_as_insufficient_context(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    encoder = DeterministicEncoder(settings.embedding_dimension)
    content = "Exact evidence requires a configured generation provider."
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            start_worker=True,
        )
    ) as client:
        _upload(client, "disabled.txt", content)
        response = client.post("/api/v1/chat/queries", json={"question": content})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "GENERATION_PROVIDER_UNAVAILABLE"
        query_id = response.json()["error"]["details"]["queryId"]
        detail = client.get(f"/api/v1/retrieval/{query_id}")
        assert detail.status_code == 200
        assert detail.json()["insufficientContext"] is False
        missing = client.get("/api/v1/retrieval/not-a-query")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "QUERY_NOT_FOUND"
