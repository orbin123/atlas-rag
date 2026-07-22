from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from phase3_support import CountingEncoderFactory, DeterministicEncoder, phase3_settings

from app.db.models import IndexState
from app.db.session import create_database_engine, create_session_factory
from app.main import create_app
from app.services.index_coordinator import rebuild_active_index
from app.services.snapshots import INDEX_FILE, verify_active_snapshot


def _app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/ingestion-jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish before timeout: {last}")


def _upload_text(client: TestClient, name: str, text: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, text.encode(), "text/plain")},
        data={"domain": "Acceptance"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    terminal = _wait_for_job(client, payload["jobId"])
    assert terminal["status"] == "succeeded", terminal
    return str(payload["documentId"]), str(payload["jobId"])


def test_empty_corpus_upload_provider_fallback_delete_and_clean_restart(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    evidence = "Exact acceptance evidence survives durable local indexing."

    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as client:
        before = client.get("/api/v1/system/info").json()
        assert before["corpus"] == {"documentCount": 0, "pageCount": 0, "chunkCount": 0}
        assert before["index"]["status"] == "not_ready"
        assert client.get("/api/v1/documents").json()["items"] == []

        document_id, _ = _upload_text(client, "acceptance.txt", evidence)
        assert client.get("/health/ready").status_code == 200

        provider_missing = client.post(
            "/api/v1/chat/queries", json={"question": evidence, "topK": 5}
        )
        assert provider_missing.status_code == 503
        assert provider_missing.json()["error"]["code"] == "GENERATION_PROVIDER_UNAVAILABLE"
        query_id = provider_missing.json()["error"]["details"]["queryId"]
        persisted = client.get(f"/api/v1/retrieval/{query_id}").json()
        assert persisted["insufficientContext"] is False
        assert persisted["sources"][0]["documentId"] == document_id

        bad_docx = client.post(
            "/api/v1/documents/upload",
            files={
                "file": (
                    "invalid.docx",
                    b"not a zip container",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert bad_docx.status_code == 422
        assert bad_docx.json()["error"]["code"] == "INVALID_FILE_CONTENT"
        binary_text = client.post(
            "/api/v1/documents/upload",
            files={"file": ("binary.txt", b"text\x00binary", "text/plain")},
        )
        assert binary_text.status_code == 422
        assert binary_text.json()["error"]["code"] == "INVALID_FILE_CONTENT"

        deletion = client.delete(f"/api/v1/documents/{document_id}")
        assert deletion.status_code == 202
        assert _wait_for_job(client, deletion.json()["jobId"])["status"] == "succeeded"
        after = client.get("/api/v1/system/info").json()
        assert after["corpus"] == {"documentCount": 0, "pageCount": 0, "chunkCount": 0}
        assert after["index"]["status"] == "ready"
        assert after["index"]["vectorCount"] == 0

        unsupported = client.post(
            "/api/v1/chat/queries",
            json={"question": "There is no evidence in this empty corpus."},
        )
        assert unsupported.status_code == 200
        assert unsupported.json()["insufficientContext"] is True
        assert unsupported.json()["sources"] == []

    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as restarted:
        assert restarted.get("/health/ready").status_code == 200
        info = restarted.get("/api/v1/system/info").json()
        assert info["corpus"]["documentCount"] == 0
        assert info["index"]["vectorCount"] == 0


def test_missing_and_corrupt_active_index_fail_closed_and_offline_rebuild_repairs(
    tmp_path: Path,
) -> None:
    settings = phase3_settings(tmp_path)
    settings.minimum_context_score = 0.9999
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    evidence = "Recovery uses persisted cleaned text and stable vector identifiers."

    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as client:
        document_id, _ = _upload_text(client, "recovery.txt", evidence)
        with _app(client).state.session_factory() as session:
            state = session.get_one(IndexState, 1)
            missing_path = settings.storage_root / state.filesystem_path / INDEX_FILE

    missing_path.unlink()
    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as missing:
        readiness = missing.get("/health/ready")
        assert readiness.status_code == 503
        assert readiness.json()["checks"]["index"]["ready"] is False
        assert readiness.json()["checks"]["worker"]["ready"] is False
        rejected = missing.post(
            "/api/v1/chat/queries", json={"question": evidence}
        )
        assert rejected.status_code == 503
        assert rejected.json()["error"]["code"] == "INDEX_INCONSISTENT"

    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        first_rebuild = rebuild_active_index(
            settings=settings,
            session_factory=session_factory,
            encoder=encoder,
            batch_size=2,
            build_reason="phase-8-missing-index-recovery",
        )
        with session_factory() as session:
            assert verify_active_snapshot(session, settings).ready is True
            state = session.get_one(IndexState, 1)
            corrupt_path = settings.storage_root / state.filesystem_path / INDEX_FILE
        assert first_rebuild.vector_count > 0
        corrupt_path.write_bytes(b"corrupt-index")
    finally:
        engine.dispose()

    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as corrupt:
        assert corrupt.get("/health/ready").status_code == 503
        assert corrupt.get("/api/v1/documents/stats").json()["indexedDocuments"] == 1

    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        second_rebuild = rebuild_active_index(
            settings=settings,
            session_factory=session_factory,
            encoder=encoder,
            batch_size=2,
            build_reason="phase-8-corrupt-index-recovery",
        )
        assert second_rebuild.vector_count == first_rebuild.vector_count
    finally:
        engine.dispose()

    with TestClient(
        create_app(settings, encoder_factory=factory, start_worker=True)
    ) as repaired:
        assert repaired.get("/health/ready").status_code == 200
        assert repaired.get(f"/api/v1/documents/{document_id}").json()["status"] == "indexed"
        provider_missing = repaired.post(
            "/api/v1/chat/queries", json={"question": evidence}
        )
        assert provider_missing.status_code == 503
        assert provider_missing.json()["error"]["code"] == "GENERATION_PROVIDER_UNAVAILABLE"
        query_id = provider_missing.json()["error"]["details"]["queryId"]
        sources = repaired.get(f"/api/v1/retrieval/{query_id}").json()["sources"]
        assert sources[0]["documentId"] == document_id
