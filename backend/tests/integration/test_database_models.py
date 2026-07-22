from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.ids import stable_vector_id
from app.db.models import Chunk, Document, DocumentPage
from app.main import create_app


@pytest.mark.integration
def test_document_children_cascade_and_constraints(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'models.db'}",
        storage_root=tmp_path / "storage",
    )
    app = create_app(settings)
    with TestClient(app):
        factory = app.state.session_factory
        chunk_id = "aaf2fd3f-cfd0-47d0-8091-f04a6f7cffef"
        with factory.begin() as session:
            document = Document(
                original_file_name="source.txt",
                safe_storage_name="generated.txt",
                file_type="txt",
                mime_type="text/plain",
                domain="test",
                source_kind="upload",
                storage_path="originals/generated.txt",
                size_bytes=12,
                sha256="a" * 64,
                page_count=1,
                chunk_count=1,
                status="indexed",
            )
            session.add(document)
            session.flush()
            session.add(
                DocumentPage(
                    document_id=document.id,
                    page_number=1,
                    raw_text="Atlas text",
                    cleaned_text="Atlas text",
                    character_count=10,
                    is_empty=False,
                    repeated_lines_removed=[],
                )
            )
            session.add(
                Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    vector_id=stable_vector_id(chunk_id),
                    chunk_index=1,
                    page_number=1,
                    original_text="Atlas text",
                    cleaned_text="Atlas text",
                    token_count=2,
                    embedding_model=settings.embedding_model,
                    embedding_revision=settings.embedding_revision,
                    embedding_dimension=settings.embedding_dimension,
                    content_sha256="b" * 64,
                    status="indexed",
                )
            )
            document_id = document.id

        with factory.begin() as session:
            session.delete(session.get_one(Document, document_id))

        with factory() as session:
            assert session.scalar(select(func.count()).select_from(DocumentPage)) == 0
            assert session.scalar(select(func.count()).select_from(Chunk)) == 0


@pytest.mark.integration
def test_database_rejects_invalid_document_status(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'invalid.db'}",
        storage_root=tmp_path / "storage",
    )
    app = create_app(settings)
    with TestClient(app), app.state.session_factory() as session:
        session.add(
            Document(
                original_file_name="source.txt",
                safe_storage_name="generated.txt",
                file_type="txt",
                mime_type="text/plain",
                domain="test",
                source_kind="upload",
                storage_path="originals/generated.txt",
                size_bytes=12,
                sha256="a" * 64,
                status="made-up",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.integration
def test_distinct_curated_paths_may_share_a_checksum(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'duplicates.db'}",
        storage_root=tmp_path / "storage",
    )
    app = create_app(settings)
    with TestClient(app), app.state.session_factory.begin() as session:
        for number in (1, 2):
            session.add(
                Document(
                    original_file_name=f"source-{number}.txt",
                    safe_storage_name=f"generated-{number}.txt",
                    file_type="txt",
                    mime_type="text/plain",
                    domain="test",
                    source_kind="bootstrap",
                    relative_source_path=f"domain/source-{number}.txt",
                    storage_path=f"originals/generated-{number}.txt",
                    size_bytes=12,
                    sha256="c" * 64,
                    status="indexed",
                )
            )
