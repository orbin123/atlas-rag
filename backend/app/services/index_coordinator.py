from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import utc_now
from app.db.models import Chunk, Document, DocumentPage, IndexState, IngestionJob
from app.services.chunking import BuiltChunk
from app.services.embedding import EmbeddingEncoder, validated_embeddings
from app.services.preprocessing import CleanedPage
from app.services.snapshots import (
    FAISS_TYPE,
    INDEX_FILE,
    MANIFEST_FILE,
    build_faiss_index,
    persist_snapshot,
    prune_snapshot_history,
    snapshot_artifact_checksums,
    verify_active_snapshot,
)


@dataclass(frozen=True, slots=True)
class IndexCommitResult:
    index: Any
    index_version: str
    vector_count: int
    page_count: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class DeletionCommitResult:
    index: Any
    index_version: str
    vector_count: int
    removed_page_count: int
    removed_chunk_count: int
    original_file_removed: bool


@dataclass(frozen=True, slots=True)
class RebuildResult:
    index: Any
    index_version: str
    vector_count: int
    previous_index_version: str | None


def _page_id(document_id: str, page_number: int) -> str:
    return str(uuid.uuid5(uuid.UUID(document_id), f"page:{page_number}"))


def _built_chunk(row: Chunk) -> BuiltChunk:
    return BuiltChunk(
        id=row.id,
        document_id=row.document_id,
        vector_id=row.vector_id,
        chunk_index=row.chunk_index,
        page_number=row.page_number,
        original_text=row.original_text,
        cleaned_text=row.cleaned_text,
        token_count=row.token_count,
        model_input_token_count=row.token_count,
        overlap_from_previous_tokens=0,
        content_sha256=row.content_sha256,
    )


def _active_inputs(
    session: Session, settings: Settings, state: IndexState | None
) -> tuple[list[BuiltChunk], dict[str, str], Any]:
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to update the index.") from exc
    if state is None:
        index: Any = faiss.IndexIDMap2(faiss.IndexFlatIP(settings.embedding_dimension))
        return [], {}, index
    snapshot_path = settings.storage_root / state.filesystem_path
    manifest = json.loads((snapshot_path / MANIFEST_FILE).read_text(encoding="utf-8"))
    order = [str(item["chunkId"]) for item in manifest["orderedBuildInputs"]]
    rows = session.scalars(select(Chunk).where(Chunk.id.in_(order))).all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(order):
        raise RuntimeError("The active manifest does not align with indexed chunks.")
    index = faiss.read_index(str(snapshot_path / INDEX_FILE))
    return (
        [_built_chunk(by_id[chunk_id]) for chunk_id in order],
        {str(key): str(value) for key, value in manifest.get("artifactChecksums", {}).items()},
        index,
    )


def _state_values(state: IndexState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "index_version": state.index_version,
        "filesystem_path": state.filesystem_path,
        "manifest_checksum": state.manifest_checksum,
        "faiss_type": state.faiss_type,
        "vector_count": state.vector_count,
        "dimension": state.dimension,
        "embedding_model": state.embedding_model,
        "embedding_revision": state.embedding_revision,
        "normalization": state.normalization,
        "chunking_configuration": state.chunking_configuration,
        "created_at": state.created_at,
        "build_reason": state.build_reason,
    }


def _apply_state(state: IndexState, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(state, key, value)


def _snapshot_state_values(
    snapshot: Any, settings: Settings, *, build_reason: str
) -> dict[str, Any]:
    return {
        "index_version": snapshot.version,
        "filesystem_path": snapshot.relative_path,
        "manifest_checksum": snapshot.manifest_checksum,
        "faiss_type": FAISS_TYPE,
        "vector_count": snapshot.vector_count,
        "dimension": snapshot.dimension,
        "embedding_model": settings.embedding_model,
        "embedding_revision": settings.embedding_revision,
        "normalization": "l2" if settings.embedding_normalize else "none",
        "chunking_configuration": {
            "version": settings.chunking_version,
            "targetTokens": settings.chunk_target_tokens,
            "maxTokens": settings.chunk_max_tokens,
            "overlapTokens": settings.chunk_overlap_tokens,
        },
        "created_at": snapshot.created_at,
        "build_reason": build_reason,
    }


def _set_index_state(
    session: Session, values: dict[str, Any], *, allow_create: bool = True
) -> None:
    state = session.get(IndexState, 1)
    if state is None:
        if not allow_create:
            raise RuntimeError("The active index state disappeared during finalization.")
        session.add(IndexState(id=1, **values))
    else:
        _apply_state(state, values)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def commit_incremental_document(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    document_id: str,
    job_id: str,
    pages: list[CleanedPage],
    chunks: list[BuiltChunk],
    vectors: Any,
) -> IndexCommitResult:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to update the index.") from exc
    lock = FileLock(settings.storage_root / "index-write.lock")
    snapshot_path: Path | None = None
    old_state_values: dict[str, Any] | None = None
    with lock:
        with session_factory() as session:
            state = session.get(IndexState, 1)
            old_state_values = _state_values(state)
            existing, checksums, candidate = _active_inputs(session, settings, state)
            document = session.get_one(Document, document_id)
            if document.status == "indexed":
                active = verify_active_snapshot(session, settings)
                if not active.ready:
                    raise RuntimeError("An already finalized document has an invalid active index.")
                return IndexCommitResult(
                    index=active.index,
                    index_version=str(active.index_version),
                    vector_count=active.vector_count,
                    page_count=document.page_count,
                    chunk_count=document.chunk_count,
                )
        existing_vector_ids = {chunk.vector_id for chunk in existing}
        if any(chunk.vector_id in existing_vector_ids for chunk in chunks):
            raise RuntimeError("A new chunk vector ID collides with the active index.")
        identifiers = np.asarray([chunk.vector_id for chunk in chunks], dtype=np.int64)
        candidate.add_with_ids(vectors, identifiers)
        all_chunks = [*existing, *chunks]
        if candidate.ntotal != len(all_chunks):
            raise RuntimeError("The candidate index count does not match its chunk inputs.")
        checksums[f"upload:{document_id}"] = document.sha256
        snapshot = persist_snapshot(
            index=candidate,
            chunks=all_chunks,
            settings=settings,
            artifact_checksums=checksums,
            build_reason=f"incremental-ingestion:{document_id}",
        )
        snapshot_path = settings.storage_root / snapshot.relative_path
        try:
            with session_factory.begin() as session:
                document = session.get_one(Document, document_id)
                job = session.get_one(IngestionJob, job_id)
                if document.status == "indexed" or job.status == "succeeded":
                    raise RuntimeError("The ingestion was finalized concurrently.")
                for page in pages:
                    session.add(
                        DocumentPage(
                            id=_page_id(document_id, page.page_number),
                            document_id=document_id,
                            page_number=page.page_number,
                            raw_text=page.raw_text,
                            cleaned_text=page.cleaned_text,
                            character_count=len(page.cleaned_text),
                            is_empty=not bool(page.cleaned_text),
                            repeated_lines_removed=list(page.repeated_lines_removed),
                        )
                    )
                for chunk in chunks:
                    session.add(
                        Chunk(
                            id=chunk.id,
                            document_id=document_id,
                            vector_id=chunk.vector_id,
                            chunk_index=chunk.chunk_index,
                            page_number=chunk.page_number,
                            original_text=chunk.original_text,
                            cleaned_text=chunk.cleaned_text,
                            token_count=chunk.token_count,
                            embedding_model=settings.embedding_model,
                            embedding_revision=settings.embedding_revision,
                            embedding_dimension=settings.embedding_dimension,
                            content_sha256=chunk.content_sha256,
                            status="indexed",
                        )
                    )
                now = snapshot.created_at
                document.page_count = len(pages)
                document.chunk_count = len(chunks)
                document.status = "processing"
                document.failure_code = None
                document.failure_message = None
                document.indexed_at = None
                job.status = "running"
                job.stage = "finalizing"
                job.progress_percent = 98
                job.stage_message = "Verifying the committed index snapshot."
                job.error_code = None
                job.error_message = None
                job.result = None
                job.heartbeat_at = now
                job.completed_at = None
                _set_index_state(
                    session,
                    _snapshot_state_values(
                        snapshot,
                        settings,
                        build_reason=f"incremental-ingestion:{document_id}",
                    ),
                )
            with session_factory() as session:
                report = verify_active_snapshot(session, settings)
            if not report.ready:
                raise RuntimeError(
                    "Post-ingestion index verification failed: " + "; ".join(report.errors)
                )
            with session_factory.begin() as session:
                document = session.get_one(Document, document_id)
                job = session.get_one(IngestionJob, job_id)
                now = utc_now()
                document.status = "indexed"
                document.indexed_at = now
                job.status = "succeeded"
                job.progress_percent = 100
                job.stage_message = "Document indexed and verified."
                job.result = {
                    "documentId": document_id,
                    "pageCount": len(pages),
                    "chunkCount": len(chunks),
                    "indexVersion": snapshot.version,
                    "vectorCount": snapshot.vector_count,
                }
                job.heartbeat_at = now
                job.completed_at = now
        except Exception:
            with session_factory.begin() as session:
                rollback_document = session.get(Document, document_id)
                if rollback_document is not None:
                    for page_row in session.scalars(
                        select(DocumentPage).where(DocumentPage.document_id == document_id)
                    ):
                        session.delete(page_row)
                    chunks_to_remove = session.scalars(
                        select(Chunk).where(Chunk.document_id == document_id)
                    )
                    for chunk_row in chunks_to_remove:
                        session.delete(chunk_row)
                    rollback_document.page_count = 0
                    rollback_document.chunk_count = 0
                    rollback_document.status = "processing"
                    rollback_document.indexed_at = None
                state = session.get(IndexState, 1)
                if old_state_values is None:
                    if state is not None:
                        session.delete(state)
                elif state is None:
                    session.add(IndexState(id=1, **old_state_values))
                else:
                    _apply_state(state, old_state_values)
                rollback_job = session.get(IngestionJob, job_id)
                if rollback_job is not None:
                    rollback_job.status = "running"
                    rollback_job.progress_percent = 90
                    rollback_job.completed_at = None
                    rollback_job.result = None
                    rollback_job.heartbeat_at = utc_now()
            if snapshot_path is not None:
                shutil.rmtree(snapshot_path, ignore_errors=True)
            raise
        previous_version = (
            str(old_state_values["index_version"]) if old_state_values is not None else None
        )
        prune_snapshot_history(
            settings,
            active_version=snapshot.version,
            previous_version=previous_version,
        )
        return IndexCommitResult(
            index=candidate,
            index_version=snapshot.version,
            vector_count=snapshot.vector_count,
            page_count=len(pages),
            chunk_count=len(chunks),
        )


def commit_document_deletion(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    document_id: str,
    job_id: str,
) -> DeletionCommitResult:
    """Remove one document through a recoverable index/DB/file finalization.

    The target chunks are first excluded from a new verified snapshot while their
    database rows remain recoverable. Only after alignment succeeds is the original
    moved aside and the document cascade committed. A retry can resume safely after
    a process interruption between those two commits.
    """

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to update the index.") from exc

    lock = FileLock(settings.storage_root / "index-write.lock")
    snapshot_path: Path | None = None
    tombstone: Path | None = None
    original_path: Path | None = None
    original_moved = False
    candidate_applied = False
    old_state_values: dict[str, Any] | None = None
    old_chunk_statuses: dict[str, str] = {}
    previous_version: str | None = None
    with lock:
        with session_factory() as session:
            state = session.get(IndexState, 1)
            if state is None:
                raise RuntimeError("Document deletion requires an active index state.")
            old_state_values = _state_values(state)
            previous_version = state.index_version
            existing, checksums, candidate = _active_inputs(session, settings, state)
            document = session.get(Document, document_id)
            job = session.get(IngestionJob, job_id)
            if document is None:
                if job is not None and job.status == "succeeded" and job.result:
                    active = verify_active_snapshot(session, settings)
                    if not active.ready:
                        raise RuntimeError("A finalized deletion has an invalid active index.")
                    return DeletionCommitResult(
                        index=active.index,
                        index_version=str(active.index_version),
                        vector_count=active.vector_count,
                        removed_page_count=int(job.result.get("pageCount", 0)),
                        removed_chunk_count=int(job.result.get("chunkCount", 0)),
                        original_file_removed=bool(job.result.get("originalFileRemoved", False)),
                    )
                raise RuntimeError("The deletion document record is missing.")
            if job is None or job.document_id != document_id:
                raise RuntimeError("The deletion job does not own this document.")
            target_rows = session.scalars(
                select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
            ).all()
            old_chunk_statuses = {row.id: row.status for row in target_rows}
            active_target = [chunk for chunk in existing if chunk.document_id == document_id]
            active_target_ids = {chunk.id for chunk in active_target}
            indexed_target_ids = {row.id for row in target_rows if row.status == "indexed"}
            if active_target_ids != indexed_target_ids:
                raise RuntimeError("The target document does not align with the active manifest.")
            removed_page_count = document.page_count
            removed_chunk_count = document.chunk_count
            root = settings.storage_root.resolve()
            resolved = (root / document.storage_path).resolve()
            if resolved == root or root not in resolved.parents:
                raise RuntimeError("The document original has an unsafe storage path.")
            original_path = resolved
            temp_root = root / "temp"
            temp_root.mkdir(parents=True, exist_ok=True)
            tombstone = temp_root / f"{document_id}.{document.safe_storage_name}.delete"

        try:
            if active_target:
                identifiers = np.asarray(
                    [chunk.vector_id for chunk in active_target], dtype=np.int64
                )
                removed = int(candidate.remove_ids(identifiers))
                if removed != len(active_target):
                    raise RuntimeError("FAISS did not remove every target vector ID.")
                remaining = [chunk for chunk in existing if chunk.document_id != document_id]
                if candidate.ntotal != len(remaining):
                    raise RuntimeError("The deletion candidate count is not aligned.")
                checksums.pop(f"upload:{document_id}", None)
                snapshot = persist_snapshot(
                    index=candidate,
                    chunks=remaining,
                    settings=settings,
                    artifact_checksums=checksums,
                    build_reason=f"document-deletion:{document_id}",
                )
                snapshot_path = settings.storage_root / snapshot.relative_path
                with session_factory.begin() as session:
                    document = session.get_one(Document, document_id)
                    job = session.get_one(IngestionJob, job_id)
                    if document.status != "deleting" or job.status != "running":
                        raise RuntimeError("The deletion lifecycle changed concurrently.")
                    for row in session.scalars(
                        select(Chunk).where(Chunk.document_id == document_id)
                    ):
                        row.status = "failed"
                    _set_index_state(
                        session,
                        _snapshot_state_values(
                            snapshot,
                            settings,
                            build_reason=f"document-deletion:{document_id}",
                        ),
                        allow_create=False,
                    )
                    job.stage = "finalizing"
                    job.progress_percent = 96
                    job.stage_message = "Verifying the index without the document."
                    job.heartbeat_at = snapshot.created_at
                candidate_applied = True
                with session_factory() as session:
                    report = verify_active_snapshot(session, settings)
                if not report.ready:
                    raise RuntimeError(
                        "Post-deletion index verification failed: " + "; ".join(report.errors)
                    )
                active_version = snapshot.version
                active_count = snapshot.vector_count
            else:
                with session_factory() as session:
                    report = verify_active_snapshot(session, settings)
                    current_state = session.get_one(IndexState, 1)
                if not report.ready:
                    raise RuntimeError(
                        "Deletion retry found an invalid active index: " + "; ".join(report.errors)
                    )
                candidate = report.index
                active_version = current_state.index_version
                active_count = current_state.vector_count

            if original_path.exists():
                if original_path.is_symlink() or not original_path.is_file():
                    raise RuntimeError("The stored original is not a safe regular file.")
                if tombstone.exists():
                    raise RuntimeError("Both the original and deletion tombstone exist.")
                os.replace(original_path, tombstone)
                original_moved = True
                _fsync_directory(original_path.parent)
                _fsync_directory(tombstone.parent)
            elif tombstone.exists():
                original_moved = True

            with session_factory.begin() as session:
                document = session.get_one(Document, document_id)
                job = session.get_one(IngestionJob, job_id)
                now = utc_now()
                job.document_id = None
                job.status = "succeeded"
                job.stage = "finalizing"
                job.progress_percent = 100
                job.stage_message = "Document and vectors deleted and verified."
                job.error_code = None
                job.error_message = None
                job.result = {
                    "documentId": document_id,
                    "pageCount": removed_page_count,
                    "chunkCount": removed_chunk_count,
                    "indexVersion": active_version,
                    "vectorCount": active_count,
                    "originalFileRemoved": original_moved or not original_path.exists(),
                }
                job.heartbeat_at = now
                job.completed_at = now
                session.delete(document)
            if tombstone.exists():
                tombstone.unlink()
                _fsync_directory(tombstone.parent)
            prune_snapshot_history(
                settings,
                active_version=active_version,
                previous_version=(previous_version if active_version != previous_version else None),
            )
            return DeletionCommitResult(
                index=candidate,
                index_version=active_version,
                vector_count=active_count,
                removed_page_count=removed_page_count,
                removed_chunk_count=removed_chunk_count,
                original_file_removed=original_moved or not original_path.exists(),
            )
        except Exception:
            if original_moved and tombstone is not None and original_path is not None:
                if tombstone.exists() and not original_path.exists():
                    os.replace(tombstone, original_path)
                    _fsync_directory(original_path.parent)
                    _fsync_directory(tombstone.parent)
            if candidate_applied:
                with session_factory.begin() as session:
                    for chunk_id, status in old_chunk_statuses.items():
                        rollback_chunk = session.get(Chunk, chunk_id)
                        if rollback_chunk is not None:
                            rollback_chunk.status = status
                    if old_state_values is None:
                        state = session.get(IndexState, 1)
                        if state is not None:
                            session.delete(state)
                    else:
                        _set_index_state(session, old_state_values)
                    document = session.get(Document, document_id)
                    if document is not None:
                        document.status = "deleting"
                    job = session.get(IngestionJob, job_id)
                    if job is not None:
                        job.status = "running"
                        job.progress_percent = 88
                        job.completed_at = None
                        job.result = None
                        job.heartbeat_at = utc_now()
            if snapshot_path is not None:
                shutil.rmtree(snapshot_path, ignore_errors=True)
            raise


def rebuild_active_index(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    encoder: EmbeddingEncoder,
    batch_size: int | None = None,
    build_reason: str = "manual-index-rebuild",
) -> RebuildResult:
    """Re-embed indexed SQLite chunks and atomically activate a repaired snapshot."""

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to rebuild the index.") from exc

    lock = FileLock(settings.storage_root / "index-write.lock")
    snapshot_path: Path | None = None
    with lock:
        with session_factory() as session:
            state = session.get(IndexState, 1)
            old_state_values = _state_values(state)
            previous_version = state.index_version if state is not None else None
            checksums = snapshot_artifact_checksums(settings, state)
            rows = session.scalars(
                select(Chunk)
                .where(Chunk.status == "indexed")
                .order_by(Chunk.document_id, Chunk.chunk_index)
            ).all()
            for row in rows:
                if (
                    row.embedding_model != settings.embedding_model
                    or row.embedding_revision != settings.embedding_revision
                    or row.embedding_dimension != settings.embedding_dimension
                ):
                    raise RuntimeError(
                        "An indexed chunk does not match the configured embedding schema."
                    )
            chunks = [_built_chunk(row) for row in rows]
        if chunks:
            vectors = validated_embeddings(
                encoder,
                [chunk.cleaned_text for chunk in chunks],
                settings,
                batch_size=batch_size or settings.embedding_batch_size,
            )
        else:
            vectors = np.empty((0, settings.embedding_dimension), dtype=np.float32)
        index = build_faiss_index(vectors, chunks, settings.embedding_dimension)
        snapshot = persist_snapshot(
            index=index,
            chunks=chunks,
            settings=settings,
            artifact_checksums=checksums,
            build_reason=build_reason,
        )
        snapshot_path = settings.storage_root / snapshot.relative_path
        try:
            with session_factory.begin() as session:
                _set_index_state(
                    session,
                    _snapshot_state_values(snapshot, settings, build_reason=build_reason),
                )
            with session_factory() as session:
                report = verify_active_snapshot(session, settings)
            if not report.ready:
                raise RuntimeError("Rebuilt index verification failed: " + "; ".join(report.errors))
        except Exception:
            with session_factory.begin() as session:
                state = session.get(IndexState, 1)
                if old_state_values is None:
                    if state is not None:
                        session.delete(state)
                elif state is None:
                    session.add(IndexState(id=1, **old_state_values))
                else:
                    _apply_state(state, old_state_values)
            if snapshot_path is not None:
                shutil.rmtree(snapshot_path, ignore_errors=True)
            raise
        prune_snapshot_history(
            settings,
            active_version=snapshot.version,
            previous_version=previous_version,
        )
        return RebuildResult(
            index=index,
            index_version=snapshot.version,
            vector_count=snapshot.vector_count,
            previous_index_version=previous_version,
        )
