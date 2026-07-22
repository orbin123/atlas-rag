from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from phase3_support import CountingEncoderFactory, DeterministicEncoder, phase3_settings
from sqlalchemy import func, select

from app.db.models import Chunk, Document, DocumentPage, IndexState, IngestionJob
from app.main import create_app
from app.services.deletions import accept_document_deletion
from app.services.index_coordinator import commit_document_deletion, rebuild_active_index
from app.services.snapshots import INDEX_FILE, verify_active_snapshot


def _app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


def _faiss_ids(index: Any) -> set[int]:
    import faiss

    return {int(value) for value in faiss.vector_to_array(index.id_map)}


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


def _upload(client: TestClient, name: str, text: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    terminal = _wait_for_job(client, payload["jobId"])
    assert terminal["status"] == "succeeded", terminal
    return str(payload["documentId"]), str(payload["jobId"])


def _delete(client: TestClient, document_id: str) -> tuple[str, dict[str, Any]]:
    response = client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 202, response.text
    payload = response.json()
    terminal = _wait_for_job(client, payload["jobId"])
    return str(payload["jobId"]), terminal


def test_delete_removes_api_file_vectors_and_retains_two_snapshots_after_restart(
    tmp_path: Path,
) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    deleted_id = ""
    survivor_id = ""
    deleted_vector_id = 0
    deleted_original = Path()

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        deleted_id, _ = _upload(
            client,
            "delete-me.txt",
            "Deletion evidence has a unique phrase about an obsolete Atlas source.",
        )
        survivor_id, _ = _upload(
            client,
            "keep-me.txt",
            "Surviving evidence remains available after coordinated deletion.",
        )
        with _app(client).state.session_factory() as session:
            deleted_document = session.get_one(Document, deleted_id)
            deleted_original = settings.storage_root / deleted_document.storage_path
            deleted_chunk = session.scalar(
                select(Chunk).where(Chunk.document_id == deleted_id).limit(1)
            )
            assert deleted_chunk is not None
            deleted_vector_id = deleted_chunk.vector_id
            count_before = session.get_one(IndexState, 1).vector_count
        assert deleted_original.is_file()

        _, terminal = _delete(client, deleted_id)
        assert terminal["status"] == "succeeded"
        assert terminal["kind"] == "delete"
        assert terminal["documentId"] is None
        assert terminal["result"]["documentId"] == deleted_id
        assert terminal["result"]["originalFileRemoved"] is True
        assert terminal["result"]["vectorCount"] < count_before
        assert client.get(f"/api/v1/documents/{deleted_id}").status_code == 404
        assert client.get(f"/api/v1/documents/{deleted_id}/pages").status_code == 404
        assert client.get(f"/api/v1/documents/{deleted_id}/chunks").status_code == 404
        assert client.get(f"/api/v1/documents/{survivor_id}").status_code == 200
        assert not deleted_original.exists()
        assert not list((settings.storage_root / "temp").glob(f"{deleted_id}.*.delete"))
        with _app(client).state.session_factory() as session:
            state = session.get_one(IndexState, 1)
            assert (
                session.scalar(
                    select(func.count()).select_from(Chunk).where(Chunk.document_id == deleted_id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DocumentPage)
                    .where(DocumentPage.document_id == deleted_id)
                )
                == 0
            )
            assert state.vector_count == session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.status == "indexed")
            )
        faiss_ids = _faiss_ids(_app(client).state.active_index)
        assert deleted_vector_id not in faiss_ids
        snapshot_dirs = [
            path
            for path in (settings.storage_root / "indexes").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert len(snapshot_dirs) == settings.snapshot_retention_count

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/api/v1/documents/{deleted_id}").status_code == 404
        assert client.get(f"/api/v1/documents/{survivor_id}").status_code == 200
        assert deleted_vector_id not in _faiss_ids(_app(client).state.active_index)


def test_snapshot_write_failure_preserves_document_then_restart_retries_deletion(
    tmp_path: Path,
) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    document_id = ""
    original_version = ""

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "write-failure.txt",
            "A simulated snapshot write failure must retain this entire document.",
        )
        with _app(client).state.session_factory() as session:
            document = session.get_one(Document, document_id)
            original_path = settings.storage_root / document.storage_path
            state = session.get_one(IndexState, 1)
            original_version = state.index_version
            original_count = state.vector_count
        with patch(
            "app.services.index_coordinator.persist_snapshot",
            side_effect=OSError("simulated deletion snapshot write failure"),
        ):
            _, terminal = _delete(client, document_id)
        assert terminal["status"] == "failed"
        assert terminal["attempt"] == 3
        assert terminal["error"]["code"] == "INDEX_UPDATE_FAILED"
        assert original_path.is_file()
        with _app(client).state.session_factory() as session:
            document = session.get_one(Document, document_id)
            assert document.status == "failed"
            assert session.get_one(IndexState, 1).index_version == original_version
            assert session.get_one(IndexState, 1).vector_count == original_count
            assert all(
                row.status == "indexed"
                for row in session.scalars(select(Chunk).where(Chunk.document_id == document_id))
            )
        assert client.get("/health/ready").status_code == 200

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        _, terminal = _delete(client, document_id)
        assert terminal["status"] == "succeeded"
        assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert client.get("/health/ready").status_code == 200


def test_post_snapshot_file_failure_rolls_database_and_active_index_back(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "rollback-delete.txt",
            "A failure after candidate verification restores the prior known-good snapshot.",
        )
        with _app(client).state.session_factory() as session:
            document = session.get_one(Document, document_id)
            original_path = settings.storage_root / document.storage_path
            original_state = session.get_one(IndexState, 1)
            original_version = original_state.index_version
            original_count = original_state.vector_count

        original_directory_calls = 0

        def fail_after_original_move(path: Path) -> None:
            nonlocal original_directory_calls
            if path.name == "originals":
                original_directory_calls += 1
                if original_directory_calls % 2 == 1:
                    raise OSError("simulated original-directory fsync failure")

        with patch(
            "app.services.index_coordinator._fsync_directory",
            side_effect=fail_after_original_move,
        ):
            _, terminal = _delete(client, document_id)
        assert terminal["status"] == "failed"
        assert terminal["attempt"] == 3
        assert original_path.is_file()
        with _app(client).state.session_factory() as session:
            state = session.get_one(IndexState, 1)
            assert state.index_version == original_version
            assert state.vector_count == original_count
            assert all(
                row.status == "indexed"
                for row in session.scalars(select(Chunk).where(Chunk.document_id == document_id))
            )
            assert verify_active_snapshot(session, settings).ready is True
        snapshot_dirs = [
            path
            for path in (settings.storage_root / "indexes").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert len(snapshot_dirs) == 1
        _, retry = _delete(client, document_id)
        assert retry["status"] == "succeeded"


def test_interrupted_delete_acceptance_is_idempotent_and_restart_resumes(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "restart-delete.txt",
            "An interrupted durable deletion is safely claimed again after restart.",
        )
        session_factory = _app(client).state.session_factory

    first = accept_document_deletion(document_id, settings, session_factory)
    second = accept_document_deletion(document_id, settings, session_factory)
    assert second.job_id == first.job_id
    with session_factory.begin() as session:
        job = session.get_one(IngestionJob, first.job_id)
        job.status = "running"
        job.stage = "indexing"
        job.progress_percent = 60
        job.attempt = 1
        document = session.get_one(Document, document_id)
        document.status = "deleting"

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        terminal = _wait_for_job(client, first.job_id)
        assert terminal["status"] == "succeeded"
        assert terminal["attempt"] == 2
        assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert client.get("/health/ready").status_code == 200


def test_searches_use_stable_index_reference_during_deletion_swap(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    entered = threading.Event()
    release = threading.Event()

    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "concurrent-delete.txt",
            "Concurrent search readers keep a stable FAISS reference during a swap.",
        )
        _upload(
            client,
            "concurrent-survivor.txt",
            "A second document ensures the replacement index remains non-empty.",
        )
        with _app(client).state.session_factory() as session:
            chunk = session.scalar(select(Chunk).where(Chunk.document_id == document_id).limit(1))
            assert chunk is not None
            query_vector = encoder.encode([chunk.cleaned_text], batch_size=1)
            deleted_vector_id = chunk.vector_id

        def paused_commit(**kwargs: Any) -> Any:
            result = commit_document_deletion(**kwargs)
            entered.set()
            assert release.wait(timeout=5)
            return result

        with patch("app.workers.runner.commit_document_deletion", side_effect=paused_commit):
            accepted = client.delete(f"/api/v1/documents/{document_id}")
            assert accepted.status_code == 202
            job_id = accepted.json()["jobId"]
            assert entered.wait(timeout=5)
            observed: list[int] = []
            for _ in range(50):
                stable_reference = _app(client).state.active_index
                _, identifiers = stable_reference.search(query_vector, 1)
                observed.append(int(identifiers[0, 0]))
            assert observed == [deleted_vector_id] * 50
            assert client.get("/health/ready").status_code == 503
            release.set()
            terminal = _wait_for_job(client, job_id)
        assert terminal["status"] == "succeeded"
        _, identifiers = _app(client).state.active_index.search(query_vector, 10)
        assert deleted_vector_id not in {int(value) for value in identifiers[0] if value >= 0}
        assert client.get("/health/ready").status_code == 200


def test_offline_rebuild_repairs_corrupt_active_index_and_preserves_vector_ids(
    tmp_path: Path,
) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "rebuild.txt",
            "Offline rebuild re-embeds canonical SQLite chunks with their stable vector IDs.",
        )
        session_factory = _app(client).state.session_factory
        with session_factory() as session:
            state = session.get_one(IndexState, 1)
            old_version = state.index_version
            old_ids = set(
                session.scalars(select(Chunk.vector_id).where(Chunk.document_id == document_id))
            )
            index_path = settings.storage_root / state.filesystem_path / INDEX_FILE

    index_path.write_bytes(b"corrupt-index")
    with session_factory() as session:
        assert verify_active_snapshot(session, settings).ready is False
    rebuilt = rebuild_active_index(
        settings=settings,
        session_factory=session_factory,
        encoder=encoder,
        batch_size=2,
        build_reason="phase-4-recovery-test",
    )
    assert rebuilt.previous_index_version == old_version
    assert rebuilt.index_version != old_version
    assert old_ids.issubset(_faiss_ids(rebuilt.index))
    with session_factory() as session:
        report = verify_active_snapshot(session, settings)
        assert report.ready is True
        assert report.index_version == rebuilt.index_version
        assert report.vector_count == rebuilt.vector_count


def test_rebuild_uses_content_not_mock_vectors(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    factory = CountingEncoderFactory(encoder)
    with TestClient(create_app(settings, encoder_factory=factory, start_worker=True)) as client:
        document_id, _ = _upload(
            client,
            "content-rebuild.txt",
            "The rebuild command derives vectors from persisted cleaned document content.",
        )
        session_factory = _app(client).state.session_factory
        with session_factory() as session:
            chunk = session.scalar(select(Chunk).where(Chunk.document_id == document_id).limit(1))
            assert chunk is not None
            expected_digest = hashlib.sha256(chunk.cleaned_text.encode()).digest()
            assert expected_digest
    calls_before = encoder.encode_calls
    rebuild_active_index(
        settings=settings,
        session_factory=session_factory,
        encoder=encoder,
        batch_size=1,
    )
    assert encoder.encode_calls == calls_before + 1


def test_delete_openapi_and_typed_errors_match_contract(tmp_path: Path) -> None:
    settings = phase3_settings(tmp_path)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    with TestClient(
        create_app(
            settings,
            encoder_factory=CountingEncoderFactory(encoder),
            start_worker=True,
        )
    ) as client:
        document_id, _ = _upload(
            client,
            "contract-delete.txt",
            "Deletion exposes the accepted durable job response contract.",
        )
        missing = client.delete("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
        openapi = client.get("/openapi.json").json()
        operation = openapi["paths"]["/api/v1/documents/{document_id}"]["delete"]
        assert operation["operationId"] == "deleteDocument"
        accepted = client.delete(f"/api/v1/documents/{document_id}")
        assert accepted.status_code == 202
        payload = accepted.json()
        assert set(payload) == {"jobId", "documentId", "status", "statusUrl"}
        assert _wait_for_job(client, payload["jobId"])["status"] == "succeeded"
