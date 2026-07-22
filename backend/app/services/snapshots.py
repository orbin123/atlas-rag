from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Chunk, IndexState
from app.services.artifacts import sha256_file
from app.services.chunking import BuiltChunk

FAISS_TYPE = "IndexIDMap2/IndexFlatIP"
INDEX_FILE = "index.faiss"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    version: str
    relative_path: str
    manifest_checksum: str
    vector_count: int
    dimension: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AlignmentReport:
    ready: bool
    errors: tuple[str, ...]
    index_version: str | None
    vector_count: int
    dimension: int | None
    index: Any | None = None


def _canonical_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _hash_ordered_inputs(chunks: Sequence[BuiltChunk]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(f"{chunk.id}:{chunk.vector_id}:{chunk.content_sha256}\n".encode())
    return digest.hexdigest()


def build_faiss_index(vectors: Any, chunks: Sequence[BuiltChunk], dimension: int) -> Any:
    try:
        import faiss
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to create a FAISS snapshot.") from exc
    if vectors.shape != (len(chunks), dimension):
        raise ValueError("Vector matrix does not align with built chunks.")
    ids = np.asarray([chunk.vector_id for chunk in chunks], dtype=np.int64)
    if len(set(ids.tolist())) != len(ids):
        raise ValueError("Vector IDs are not unique.")
    index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
    index.add_with_ids(vectors, ids)
    if index.ntotal != len(chunks):
        raise ValueError("FAISS did not retain every vector.")
    return index


def persist_snapshot(
    *,
    index: Any,
    chunks: Sequence[BuiltChunk],
    settings: Settings,
    artifact_checksums: dict[str, str],
    build_reason: str,
) -> SnapshotRecord:
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError("Install the backend 'ml' extra to create a FAISS snapshot.") from exc
    created_at = datetime.now(UTC)
    version_seed = (
        f"{created_at.isoformat()}:{_hash_ordered_inputs(chunks)}:{settings.embedding_revision}"
    )
    version_digest = hashlib.sha256(version_seed.encode()).hexdigest()[:12]
    version = f"atlas-{created_at:%Y%m%dT%H%M%SZ}-{version_digest}"
    indexes_root = settings.storage_root.resolve() / "indexes"
    indexes_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=indexes_root))
    final = indexes_root / version
    try:
        index_path = staging / INDEX_FILE
        faiss.write_index(index, str(index_path))
        _fsync_file(index_path)
        index_sha = sha256_file(index_path)
        manifest = {
            "schemaVersion": 1,
            "applicationSchemaVersion": "20260720_0002",
            "indexVersion": version,
            "createdAt": created_at.isoformat().replace("+00:00", "Z"),
            "buildReason": build_reason,
            "faissType": FAISS_TYPE,
            "dimension": settings.embedding_dimension,
            "vectorCount": len(chunks),
            "embedding": {
                "model": settings.embedding_model,
                "revision": settings.embedding_revision,
                "normalization": "l2" if settings.embedding_normalize else "none",
            },
            "chunking": {
                "version": settings.chunking_version,
                "targetTokens": settings.chunk_target_tokens,
                "maxTokens": settings.chunk_max_tokens,
                "overlapTokens": settings.chunk_overlap_tokens,
            },
            "indexSha256": index_sha,
            "orderedBuildInputsSha256": _hash_ordered_inputs(chunks),
            "orderedBuildInputs": [
                {
                    "chunkId": chunk.id,
                    "vectorId": chunk.vector_id,
                    "contentSha256": chunk.content_sha256,
                }
                for chunk in chunks
            ],
            "artifactChecksums": artifact_checksums,
        }
        manifest_path = staging / MANIFEST_FILE
        manifest_path.write_bytes(_canonical_json(manifest))
        _fsync_file(manifest_path)
        manifest_checksum = sha256_file(manifest_path)
        os.replace(staging, final)
        directory_fd = os.open(indexes_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return SnapshotRecord(
        version=version,
        relative_path=str(Path("indexes") / version),
        manifest_checksum=manifest_checksum,
        vector_count=len(chunks),
        dimension=settings.embedding_dimension,
        created_at=created_at,
    )


def _resolve_snapshot_path(settings: Settings, relative_path: str) -> Path:
    root = settings.storage_root.resolve()
    path = (root / relative_path).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Index state contains an unsafe snapshot path.")
    return path


def snapshot_artifact_checksums(settings: Settings, state: IndexState | None) -> dict[str, str]:
    """Return provenance checksums from the active manifest when it is readable.

    Rebuild remains a recovery operation even when the active manifest is damaged,
    so a malformed or missing manifest deliberately degrades to an empty provenance
    map instead of preventing reconstruction from SQLite.
    """

    if state is None:
        return {}
    try:
        path = _resolve_snapshot_path(settings, state.filesystem_path) / MANIFEST_FILE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        values = manifest.get("artifactChecksums", {})
        if not isinstance(values, dict):
            return {}
        return {str(key): str(value) for key, value in values.items()}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def prune_snapshot_history(
    settings: Settings,
    *,
    active_version: str,
    previous_version: str | None = None,
) -> tuple[str, ...]:
    """Keep the active snapshot and a bounded known-good recovery history.

    Callers hold the index writer lock. Dot-prefixed staging directories and
    directories without a valid Atlas manifest are left untouched for diagnostics;
    only completed Atlas snapshots are eligible for pruning.
    """

    indexes_root = settings.storage_root.resolve() / "indexes"
    if not indexes_root.exists():
        return ()
    completed: list[tuple[datetime, str, Path]] = []
    for path in indexes_root.iterdir():
        if not path.is_dir() or path.name.startswith("."):
            continue
        try:
            manifest = json.loads((path / MANIFEST_FILE).read_text(encoding="utf-8"))
            version = str(manifest["indexVersion"])
            created_at = datetime.fromisoformat(str(manifest["createdAt"]).replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if version != path.name:
            continue
        completed.append((created_at, version, path))

    keep = {active_version}
    if previous_version:
        keep.add(previous_version)
    for _, version, _ in sorted(completed, reverse=True):
        if len(keep) >= settings.snapshot_retention_count:
            break
        keep.add(version)
    removed: list[str] = []
    for _, version, path in completed:
        if version in keep:
            continue
        shutil.rmtree(path)
        removed.append(version)
    if removed:
        directory_fd = os.open(indexes_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return tuple(sorted(removed))


def verify_active_snapshot(session: Session, settings: Settings) -> AlignmentReport:
    state = session.get(IndexState, 1)
    if state is None:
        return AlignmentReport(False, ("No active index state exists.",), None, 0, None)
    errors: list[str] = []
    try:
        import faiss
        import numpy as np
    except ImportError:
        return AlignmentReport(
            False,
            ("The backend 'ml' extra is not installed.",),
            state.index_version,
            state.vector_count,
            state.dimension,
        )
    try:
        snapshot = _resolve_snapshot_path(settings, state.filesystem_path)
        manifest_path = snapshot / MANIFEST_FILE
        index_path = snapshot / INDEX_FILE
        if sha256_file(manifest_path) != state.manifest_checksum:
            errors.append("Manifest checksum does not match index state.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        configured = {
            "model": settings.embedding_model,
            "revision": settings.embedding_revision,
            "dimension": settings.embedding_dimension,
            "chunking": {
                "version": settings.chunking_version,
                "targetTokens": settings.chunk_target_tokens,
                "maxTokens": settings.chunk_max_tokens,
                "overlapTokens": settings.chunk_overlap_tokens,
            },
        }
        if manifest.get("indexVersion") != state.index_version:
            errors.append("Manifest version does not match index state.")
        if manifest.get("applicationSchemaVersion") != "20260720_0002":
            errors.append("Manifest application schema is not supported.")
        if manifest.get("faissType") != FAISS_TYPE or state.faiss_type != FAISS_TYPE:
            errors.append("FAISS type does not match the supported index type.")
        if manifest.get("vectorCount") != state.vector_count:
            errors.append("Manifest vector count does not match index state.")
        if manifest.get("embedding", {}).get("model") != configured["model"]:
            errors.append("Embedding model does not match settings.")
        if manifest.get("embedding", {}).get("revision") != configured["revision"]:
            errors.append("Embedding revision does not match settings.")
        if manifest.get("dimension") != configured["dimension"]:
            errors.append("Embedding dimension does not match settings.")
        if manifest.get("chunking") != configured["chunking"]:
            errors.append("Chunking configuration does not match settings.")
        if state.embedding_model != settings.embedding_model:
            errors.append("Index-state embedding model does not match settings.")
        if state.embedding_revision != settings.embedding_revision:
            errors.append("Index-state embedding revision does not match settings.")
        if state.normalization != ("l2" if settings.embedding_normalize else "none"):
            errors.append("Index-state normalization does not match settings.")
        if state.chunking_configuration != configured["chunking"]:
            errors.append("Index-state chunking configuration does not match settings.")
        if sha256_file(index_path) != manifest.get("indexSha256"):
            errors.append("FAISS checksum does not match the manifest.")
        index = faiss.read_index(str(index_path))
        id_mapped_index: Any = index
        ids = np.asarray(faiss.vector_to_array(id_mapped_index.id_map), dtype=np.int64)
        database_rows = session.execute(
            select(Chunk.id, Chunk.vector_id, Chunk.content_sha256)
            .where(Chunk.status == "indexed")
            .order_by(Chunk.document_id, Chunk.chunk_index)
        ).all()
        database_ids = {int(row.vector_id) for row in database_rows}
        manifest_inputs = manifest.get("orderedBuildInputs", [])
        manifest_ids = [int(row["vectorId"]) for row in manifest_inputs]
        manifest_mapping = {
            (str(row["chunkId"]), int(row["vectorId"]), str(row["contentSha256"]))
            for row in manifest_inputs
        }
        database_mapping = {
            (str(row.id), int(row.vector_id), str(row.content_sha256)) for row in database_rows
        }
        if index.ntotal != state.vector_count or index.d != state.dimension:
            errors.append("FAISS count or dimension does not match index state.")
        if len(ids) != len(set(ids.tolist())):
            errors.append("FAISS contains duplicate vector IDs.")
        if set(ids.tolist()) != database_ids:
            errors.append("FAISS and database vector ID sets differ.")
        if ids.tolist() != manifest_ids:
            errors.append("FAISS vector ID order differs from the manifest.")
        if manifest_mapping != database_mapping:
            errors.append("Manifest build inputs and database chunks differ.")
        if len(manifest_inputs) != state.vector_count:
            errors.append("Manifest vector count does not match index state.")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
        errors.append(f"Snapshot validation failed: {exc}")
        index = None
    return AlignmentReport(
        ready=not errors,
        errors=tuple(errors),
        index_version=state.index_version,
        vector_count=state.vector_count,
        dimension=state.dimension,
        index=index if not errors else None,
    )
