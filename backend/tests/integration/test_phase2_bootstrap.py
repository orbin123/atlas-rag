from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.db.migrations import upgrade_database
from app.db.models import Chunk, Document, DocumentPage, EvaluationResult, IndexState
from app.db.session import create_database_engine, create_session_factory
from app.main import create_app
from app.services.artifacts import ArtifactBundle, InventoryRecord, PageRecord
from app.services.bootstrap import bootstrap_existing_corpus
from app.services.chunking import PageInput, build_chunks
from app.services.snapshots import verify_active_snapshot


class WordTokenizer:
    def __init__(self) -> None:
        self.words: dict[str, int] = {}
        self.reverse: dict[int, str] = {}

    def encode(
        self, text: str, *, add_special_tokens: bool = False, truncation: bool = False
    ) -> list[int]:
        del truncation
        identifiers: list[int] = []
        for word in text.split():
            if word not in self.words:
                identifier = len(self.words) + 10
                self.words[word] = identifier
                self.reverse[identifier] = word
            identifiers.append(self.words[word])
        return [1, *identifiers, 2] if add_special_tokens else identifiers

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        return " ".join(self.reverse[token] for token in token_ids)

    def __call__(self, text: str, **_: object) -> dict[str, Any]:
        return {"input_ids": self.encode(text, add_special_tokens=True)}


class DeterministicEncoder:
    tokenizer = WordTokenizer()

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def encode(self, texts: Any, *, batch_size: int) -> Any:
        del batch_size
        vectors = []
        for text in texts:
            digest = hashlib.sha256(str(text).encode()).digest()
            vector = np.asarray(
                [digest[index] + 1 for index in range(self.dimension)], dtype=np.float32
            )
            vector /= np.linalg.norm(vector)
            vectors.append(vector)
        return np.asarray(vectors, dtype=np.float32)


def make_bundle(
    tmp_path: Path, settings: Settings, encoder: DeterministicEncoder
) -> ArtifactBundle:
    source = tmp_path / "source.txt"
    source.write_text("Atlas alpha beta gamma. Delta epsilon zeta eta. Theta iota kappa lambda.")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    document = InventoryRecord(
        legacy_document_id="doc_test",
        file_name="source.txt",
        file_type="txt",
        domain="Test domain",
        relative_path="test/source.txt",
        source_path=source,
        size_bytes=source.stat().st_size,
        ingested_at=datetime(2026, 1, 2, tzinfo=UTC),
        sha256=source_sha,
    )
    page = PageRecord(
        legacy_document_id="doc_test",
        file_name="source.txt",
        domain="Test domain",
        file_type="txt",
        relative_path="test/source.txt",
        page_number=1,
        raw_text=source.read_text(),
        cleaned_text=source.read_text(),
        repeated_lines_removed_count=0,
    )
    document_id = str(
        uuid.uuid5(
            uuid.UUID("3f074455-a91d-4e72-aaf4-8b24af90d497"),
            f"{document.relative_path}:{source_sha}",
        )
    )
    count = len(
        build_chunks(
            [PageInput(document_id=document_id, page_number=1, cleaned_text=page.cleaned_text)],
            encoder.tokenizer,
            settings,
        )
    )
    gold = {
        "evaluation_id": "test_1",
        "domain": "Test domain",
        "question": "What does Atlas contain?",
        "answerable": True,
        "supporting_document": "source.txt",
        "supporting_page": 1,
    }
    evaluation = {
        **gold,
        "first_relevant_rank": 1,
        "reciprocal_rank": 1.0,
        "top_score": 0.8,
        "top_file_name": "source.txt",
        "retrieval_seconds": 0.01,
        "recall_at_1": True,
        "recall_at_3": True,
        "recall_at_5": True,
        "recall_at_10": True,
        "results": [{"page_number": 1}],
    }
    return ArtifactBundle(
        documents=(document,),
        pages=(page,),
        gold_questions=(gold,),
        evaluation_results=(evaluation,),
        checksums={"evaluation_results": "e" * 64, "cleaned_pages": "c" * 64},
        legacy_chunk_count=1,
        legacy_dimension=settings.embedding_dimension,
        selected_chunk_count=count,
        gold_dataset_sha256="g" * 64,
    )


@pytest.mark.integration
def test_bootstrap_is_idempotent_restart_safe_and_serves_read_contracts(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'atlas.db'}",
        storage_root=tmp_path / "storage",
        embedding_dimension=4,
        embedding_max_input_tokens=8,
        chunk_target_tokens=4,
        chunk_max_tokens=6,
        chunk_overlap_tokens=2,
    )
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    encoder = DeterministicEncoder(settings.embedding_dimension)
    bundle = make_bundle(tmp_path, settings, encoder)
    with patch("app.services.bootstrap.read_artifact_bundle", return_value=bundle):
        first = bootstrap_existing_corpus(
            repository_root=tmp_path,
            settings=settings,
            session_factory=factory,
            encoder=encoder,
            validate_legacy_vectors=False,
        )
        second = bootstrap_existing_corpus(
            repository_root=tmp_path,
            settings=settings,
            session_factory=factory,
            encoder=encoder,
            validate_legacy_vectors=False,
        )

    assert first.status == "bootstrapped"
    assert second.status == "already_bootstrapped"
    assert second.index_version == first.index_version
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentPage)) == 1
        assert session.scalar(select(func.count()).select_from(Chunk)) == first.chunk_count
        assert session.scalar(select(func.count()).select_from(EvaluationResult)) == 1
        report = verify_active_snapshot(session, settings)
        document_id = session.scalar(select(Document.id))
        state = session.get_one(IndexState, 1)
    assert report.ready
    manifest = json.loads(
        (settings.storage_root / state.filesystem_path / "manifest.json").read_text()
    )
    assert manifest["vectorCount"] == first.chunk_count
    assert len(manifest["orderedBuildInputs"]) == first.chunk_count
    assert len(list((settings.storage_root / "originals").iterdir())) == 1
    engine.dispose()

    with TestClient(create_app(settings)) as client:
        info = client.get("/api/v1/system/info").json()
        assert info["corpus"]["documentCount"] == 1
        assert info["index"]["status"] == "ready"
        listing = client.get("/api/v1/documents?pageSize=1&search=source").json()
        assert listing["total"] == 1
        assert listing["totalPages"] == 1
        assert listing["items"][0]["createdAt"].endswith("Z")
        stats = client.get("/api/v1/documents/stats").json()
        assert stats["indexHealth"]["status"] == "ready"
        assert stats["totalChunks"] == first.chunk_count
        detail = client.get(f"/api/v1/documents/{document_id}").json()
        assert detail["relativeSourcePath"] == "test/source.txt"
        assert "storagePath" not in detail
        assert detail["embedding"]["dimension"] == 4
        pages = client.get(f"/api/v1/documents/{document_id}/pages?text=raw").json()
        assert pages["items"][0]["textKind"] == "raw"
        chunks = client.get(
            f"/api/v1/documents/{document_id}/chunks?search=Atlas&pageSize=100"
        ).json()
        assert chunks["total"] >= 1
        assert chunks["items"][0]["documentName"] == "source.txt"
        missing = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    verification_engine = create_database_engine(settings.database_url)
    verification_factory = create_session_factory(verification_engine)
    with verification_factory.begin() as session:
        first_chunk_id = session.scalar(select(Chunk.id).limit(1))
        session.execute(update(Chunk).where(Chunk.id == first_chunk_id).values(vector_id=987654321))
    with verification_factory() as session:
        mismatch = verify_active_snapshot(session, settings)
    verification_engine.dispose()
    assert not mismatch.ready
    assert "vector ID sets differ" in "; ".join(mismatch.errors)
