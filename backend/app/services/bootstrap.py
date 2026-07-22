from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from filelock import FileLock
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    Chunk,
    Document,
    DocumentPage,
    EvaluationResult,
    EvaluationRun,
    IndexState,
    IngestionJob,
)
from app.services.artifacts import ArtifactBundle, read_artifact_bundle, sha256_file
from app.services.chunking import BuiltChunk, PageInput, build_chunks
from app.services.embedding import (
    EmbeddingEncoder,
    SentenceTransformerEncoder,
    validated_embeddings,
)
from app.services.snapshots import (
    FAISS_TYPE,
    SnapshotRecord,
    build_faiss_index,
    persist_snapshot,
    verify_active_snapshot,
)

BOOTSTRAP_NAMESPACE = uuid.UUID("3f074455-a91d-4e72-aaf4-8b24af90d497")
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


class BootstrapConflictError(RuntimeError):
    """Raised when bootstrap would overwrite or merge with an unknown active corpus."""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    status: str
    document_count: int
    page_count: int
    chunk_count: int
    evaluation_count: int
    index_version: str
    manifest_checksum: str


@contextmanager
def _remove_snapshot_on_failure(path: Path) -> Iterator[None]:
    try:
        yield
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise


def _document_id(relative_path: str, source_sha256: str) -> str:
    return str(uuid.uuid5(BOOTSTRAP_NAMESPACE, f"{relative_path}:{source_sha256}"))


def _page_id(document_id: str, page_number: int) -> str:
    return str(uuid.uuid5(uuid.UUID(document_id), f"page:{page_number}"))


def _evaluation_run_id(bundle: ArtifactBundle) -> str:
    source = (
        f"legacy-evaluation:{bundle.gold_dataset_sha256}:{bundle.checksums['evaluation_results']}"
    )
    return str(uuid.uuid5(BOOTSTRAP_NAMESPACE, source))


def _metric_summary(rows: tuple[dict[str, Any], ...]) -> dict[str, float | int | None]:
    answerable = [row for row in rows if bool(row["answerable"])]
    count = len(answerable)

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "answerableQuestions": count,
        "unsupportedQuestions": len(rows) - count,
        "recallAt1": mean([float(bool(row.get("recall_at_1"))) for row in answerable]),
        "recallAt3": mean([float(bool(row.get("recall_at_3"))) for row in answerable]),
        "recallAt5": mean([float(bool(row.get("recall_at_5"))) for row in answerable]),
        "recallAt10": mean([float(bool(row.get("recall_at_10"))) for row in answerable]),
        "mrr": mean([float(row.get("reciprocal_rank") or 0) for row in answerable]),
        "meanRetrievalLatencyMs": mean([float(row["retrieval_seconds"]) * 1000 for row in rows]),
        "fallbackAccuracy": None,
        "citationRate": None,
        "answerCorrectness": None,
        "groundedness": None,
        "importedLegacyRun": True,
    }


def _copy_originals(
    bundle: ArtifactBundle, settings: Settings, ids: dict[str, str]
) -> dict[str, str]:
    originals = settings.storage_root / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for document in bundle.documents:
        document_id = ids[document.legacy_document_id]
        suffix = Path(document.file_name).suffix.lower()
        safe_name = f"{document_id}{suffix}"
        destination = originals / safe_name
        if destination.exists():
            if sha256_file(destination) != document.sha256:
                raise BootstrapConflictError(f"Stored original checksum mismatch: {safe_name}")
        else:
            temporary = originals / f".{safe_name}.tmp"
            shutil.copyfile(document.source_path, temporary)
            if sha256_file(temporary) != document.sha256:
                temporary.unlink(missing_ok=True)
                raise BootstrapConflictError(f"Copied original checksum mismatch: {safe_name}")
            temporary.replace(destination)
        paths[document.legacy_document_id] = str(Path("originals") / safe_name)
    return paths


def _create_evaluation_records(
    session: Any, bundle: ArtifactBundle, snapshot: SnapshotRecord
) -> None:
    gold_by_id = {row["evaluation_id"]: row for row in bundle.gold_questions}
    run = EvaluationRun(
        id=_evaluation_run_id(bundle),
        mode="retrieval",
        dataset_version=f"atlas-gold-{bundle.gold_dataset_sha256[:12]}",
        dataset_hash=bundle.gold_dataset_sha256,
        configuration={
            "imported": True,
            "legacyIndexCompatibleWithActive": False,
            "sourceArtifact": "artifacts/evaluation/retrieval_results.jsonl",
        },
        index_version=None,
        status="succeeded",
        progress_percent=100,
        total_questions=len(bundle.evaluation_results),
        evaluated_questions=len(bundle.evaluation_results),
        summary_metrics=_metric_summary(bundle.evaluation_results),
        created_at=snapshot.created_at,
        started_at=snapshot.created_at,
        completed_at=snapshot.created_at,
    )
    session.add(run)
    for row in bundle.evaluation_results:
        gold = gold_by_id[row["evaluation_id"]]
        answerable = bool(row["answerable"])
        retrieved = row.get("results") or []
        top = retrieved[0] if retrieved else {}
        top_page = top.get("page_number")
        rank = row.get("first_relevant_rank")
        failure_category = None
        if answerable and rank is None:
            failure_category = "Expected Source Missing"
        elif answerable and int(cast(str | int, rank)) > 5:
            failure_category = "Incorrect Rank"
        session.add(
            EvaluationResult(
                run_id=run.id,
                evaluation_id=str(row["evaluation_id"]),
                domain=str(row["domain"]),
                question=str(row["question"]),
                answerable=answerable,
                expected_document_name=gold.get("supporting_document"),
                expected_page_number=gold.get("supporting_page"),
                first_relevant_rank=(int(cast(str | int, rank)) if rank is not None else None),
                recall_at_1=bool(row.get("recall_at_1")) if answerable else None,
                recall_at_3=bool(row.get("recall_at_3")) if answerable else None,
                recall_at_5=bool(row.get("recall_at_5")) if answerable else None,
                recall_at_10=bool(row.get("recall_at_10")) if answerable else None,
                mrr_contribution=float(row.get("reciprocal_rank") or 0) if answerable else None,
                top_score=float(row["top_score"]) if row.get("top_score") is not None else None,
                top_document_name=row.get("top_file_name"),
                top_page_number=(int(cast(str | int, top_page)) if top_page is not None else None),
                retrieval_latency_ms=float(row["retrieval_seconds"]) * 1000,
                failure_category=failure_category,
                failure_summary=(
                    "Imported legacy retrieval did not rank the expected source in the top five."
                    if failure_category
                    else None
                ),
            )
        )


def _existing_result(factory: sessionmaker[Any], settings: Settings) -> BootstrapResult | None:
    with factory() as session:
        document_count = int(session.scalar(select(func.count()).select_from(Document)) or 0)
        state = session.get(IndexState, 1)
        if document_count == 0 and state is None:
            return None
        report = verify_active_snapshot(session, settings)
        if not report.ready or state is None:
            details = "; ".join(report.errors)
            raise BootstrapConflictError(f"Existing corpus/index is not safely reusable: {details}")
        return BootstrapResult(
            status="already_bootstrapped",
            document_count=document_count,
            page_count=int(session.scalar(select(func.count()).select_from(DocumentPage)) or 0),
            chunk_count=int(session.scalar(select(func.count()).select_from(Chunk)) or 0),
            evaluation_count=int(
                session.scalar(select(func.count()).select_from(EvaluationResult)) or 0
            ),
            index_version=state.index_version,
            manifest_checksum=state.manifest_checksum,
        )


def bootstrap_existing_corpus(
    *,
    repository_root: Path,
    settings: Settings,
    session_factory: sessionmaker[Any],
    encoder: EmbeddingEncoder | None = None,
    batch_size: int = 32,
    validate_legacy_vectors: bool = True,
) -> BootstrapResult:
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    lock = FileLock(settings.storage_root / "bootstrap.lock")
    with lock:
        bundle = read_artifact_bundle(
            repository_root,
            settings,
            validate_legacy_vectors=validate_legacy_vectors,
        )
        existing = _existing_result(session_factory, settings)
        if existing is not None:
            if existing.document_count != len(bundle.documents):
                raise BootstrapConflictError(
                    "Existing document count differs from bootstrap inputs."
                )
            if existing.chunk_count != bundle.selected_chunk_count:
                raise BootstrapConflictError(
                    "Existing chunk count differs from accepted benchmark."
                )
            return existing

        ids = {
            row.legacy_document_id: _document_id(row.relative_path, row.sha256)
            for row in bundle.documents
        }
        storage_paths = _copy_originals(bundle, settings, ids)
        resolved_encoder = encoder or SentenceTransformerEncoder(settings)
        page_inputs = [
            PageInput(
                document_id=ids[row.legacy_document_id],
                page_number=row.page_number,
                cleaned_text=row.cleaned_text,
            )
            for row in bundle.pages
        ]
        chunks = build_chunks(page_inputs, resolved_encoder.tokenizer, settings)
        if len(chunks) != bundle.selected_chunk_count:
            raise BootstrapConflictError(
                f"Rebuilt {len(chunks)} chunks; accepted benchmark records "
                f"{bundle.selected_chunk_count}."
            )
        vectors = validated_embeddings(
            resolved_encoder,
            [chunk.cleaned_text for chunk in chunks],
            settings,
            batch_size=batch_size,
        )
        index = build_faiss_index(vectors, chunks, settings.embedding_dimension)
        snapshot = persist_snapshot(
            index=index,
            chunks=chunks,
            settings=settings,
            artifact_checksums=bundle.checksums,
            build_reason="phase-2-existing-corpus-bootstrap",
        )
        chunks_by_document: dict[str, list[BuiltChunk]] = {}
        for chunk in chunks:
            chunks_by_document.setdefault(chunk.document_id, []).append(chunk)
        pages_by_legacy_document: dict[str, list[Any]] = {}
        for page in bundle.pages:
            pages_by_legacy_document.setdefault(page.legacy_document_id, []).append(page)

        snapshot_path = settings.storage_root / snapshot.relative_path
        with _remove_snapshot_on_failure(snapshot_path), session_factory.begin() as session:
            now = snapshot.created_at
            for source in bundle.documents:
                document_id = ids[source.legacy_document_id]
                source_pages = pages_by_legacy_document.get(source.legacy_document_id, [])
                source_chunks = chunks_by_document.get(document_id, [])
                safe_name = Path(storage_paths[source.legacy_document_id]).name
                session.add(
                    Document(
                        id=document_id,
                        original_file_name=source.file_name,
                        safe_storage_name=safe_name,
                        file_type=source.file_type,
                        mime_type=MIME_TYPES[source.file_type],
                        domain=source.domain,
                        source_kind="bootstrap",
                        relative_source_path=source.relative_path,
                        storage_path=storage_paths[source.legacy_document_id],
                        size_bytes=source.size_bytes,
                        sha256=source.sha256,
                        page_count=len(source_pages),
                        chunk_count=len(source_chunks),
                        status="indexed",
                        created_at=source.ingested_at,
                        updated_at=now,
                        indexed_at=now,
                    )
                )
                for page in source_pages:
                    session.add(
                        DocumentPage(
                            id=_page_id(document_id, page.page_number),
                            document_id=document_id,
                            page_number=page.page_number,
                            raw_text=page.raw_text,
                            cleaned_text=page.cleaned_text,
                            character_count=len(page.cleaned_text),
                            is_empty=not bool(page.cleaned_text.strip()),
                            repeated_lines_removed=[],
                        )
                    )
                for chunk in source_chunks:
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
            _create_evaluation_records(session, bundle, snapshot)
            session.add(
                IngestionJob(
                    kind="bootstrap",
                    status="succeeded",
                    stage="finalizing",
                    progress_percent=100,
                    stage_message="Existing corpus imported and index verified.",
                    attempt=1,
                    max_attempts=1,
                    result={
                        "documentCount": len(bundle.documents),
                        "pageCount": len(bundle.pages),
                        "chunkCount": len(chunks),
                        "indexVersion": snapshot.version,
                    },
                    started_at=now,
                    heartbeat_at=now,
                    completed_at=now,
                )
            )
            session.add(
                IndexState(
                    id=1,
                    index_version=snapshot.version,
                    filesystem_path=snapshot.relative_path,
                    manifest_checksum=snapshot.manifest_checksum,
                    faiss_type=FAISS_TYPE,
                    vector_count=snapshot.vector_count,
                    dimension=snapshot.dimension,
                    embedding_model=settings.embedding_model,
                    embedding_revision=settings.embedding_revision,
                    normalization="l2" if settings.embedding_normalize else "none",
                    chunking_configuration={
                        "version": settings.chunking_version,
                        "targetTokens": settings.chunk_target_tokens,
                        "maxTokens": settings.chunk_max_tokens,
                        "overlapTokens": settings.chunk_overlap_tokens,
                    },
                    created_at=now,
                    build_reason="phase-2-existing-corpus-bootstrap",
                )
            )

        with session_factory() as session:
            report = verify_active_snapshot(session, settings)
            if not report.ready:
                raise BootstrapConflictError(
                    "Post-bootstrap alignment failed: " + "; ".join(report.errors)
                )
        return BootstrapResult(
            status="bootstrapped",
            document_count=len(bundle.documents),
            page_count=len(bundle.pages),
            chunk_count=len(chunks),
            evaluation_count=len(bundle.evaluation_results),
            index_version=snapshot.version,
            manifest_checksum=snapshot.manifest_checksum,
        )


def result_as_json(result: BootstrapResult) -> str:
    return json.dumps(
        {
            "status": result.status,
            "documentCount": result.document_count,
            "pageCount": result.page_count,
            "chunkCount": result.chunk_count,
            "evaluationCount": result.evaluation_count,
            "indexVersion": result.index_version,
            "manifestChecksum": result.manifest_checksum,
        },
        indent=2,
    )
