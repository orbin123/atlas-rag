from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings


class ArtifactValidationError(ValueError):
    """Raised when saved corpus artifacts cannot be trusted for bootstrap."""


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    legacy_document_id: str
    file_name: str
    file_type: str
    domain: str
    relative_path: str
    source_path: Path
    size_bytes: int
    ingested_at: datetime
    sha256: str


@dataclass(frozen=True, slots=True)
class PageRecord:
    legacy_document_id: str
    file_name: str
    domain: str
    file_type: str
    relative_path: str
    page_number: int
    raw_text: str
    cleaned_text: str
    repeated_lines_removed_count: int


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    documents: tuple[InventoryRecord, ...]
    pages: tuple[PageRecord, ...]
    gold_questions: tuple[dict[str, Any], ...]
    evaluation_results: tuple[dict[str, Any], ...]
    checksums: dict[str, str]
    legacy_chunk_count: int
    legacy_dimension: int
    selected_chunk_count: int
    gold_dataset_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_file(path: Path) -> Path:
    if not path.is_file():
        raise ArtifactValidationError(f"Required artifact is missing: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_require_file(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ArtifactValidationError(f"Invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ArtifactValidationError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path, required: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with _require_file(path).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or not required <= value.keys():
                    missing = sorted(required - value.keys()) if isinstance(value, dict) else []
                    raise ArtifactValidationError(
                        f"Invalid row {line_number} in {path}; missing fields: {missing}"
                    )
                rows.append(value)
    except (json.JSONDecodeError, OSError) as exc:
        raise ArtifactValidationError(f"Invalid JSONL artifact: {path}") from exc
    return rows


def _unique(rows: Iterable[dict[str, Any]], fields: tuple[str, ...], label: str) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in seen:
            raise ArtifactValidationError(f"Duplicate {label}: {key}")
        seen.add(key)


def _safe_source(corpus_root: Path, relative_path: str) -> Path:
    candidate = (corpus_root / relative_path).resolve()
    root = corpus_root.resolve()
    if candidate == root or root not in candidate.parents:
        raise ArtifactValidationError(f"Unsafe corpus path: {relative_path}")
    return _require_file(candidate)


def _validate_legacy_vectors(
    pipeline_root: Path, expected_count: int, expected_dimension: int
) -> None:
    try:
        import faiss
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise ArtifactValidationError(
            "The 'ml' extra is required to validate legacy vectors."
        ) from exc

    embeddings = np.load(_require_file(pipeline_root / "embeddings.npy"), mmap_mode="r")
    if embeddings.shape != (expected_count, expected_dimension):
        raise ArtifactValidationError(
            f"Legacy embedding shape {embeddings.shape} does not match "
            f"({expected_count}, {expected_dimension})."
        )
    if not np.isfinite(embeddings).all():
        raise ArtifactValidationError("Legacy embeddings contain non-finite values.")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        raise ArtifactValidationError("Legacy embeddings are not normalized.")
    index = faiss.read_index(str(_require_file(pipeline_root / "faiss.index")))
    if index.ntotal != expected_count or index.d != expected_dimension:
        raise ArtifactValidationError("Legacy FAISS count or dimension does not match metadata.")


def read_artifact_bundle(
    repository_root: Path,
    settings: Settings,
    *,
    validate_legacy_vectors: bool = True,
) -> ArtifactBundle:
    preprocessing = repository_root / "artifacts" / "preprocessing"
    pipeline = repository_root / "artifacts" / "pipeline"
    evaluation = repository_root / "artifacts" / "evaluation"
    benchmark = repository_root / "artifacts" / "benchmarks" / "embedding_context"
    corpus_root = repository_root / "data" / "atlas60"
    paths = {
        "inventory": preprocessing / "document_inventory.csv",
        "extracted_pages": preprocessing / "extracted_pages.jsonl",
        "cleaned_pages": preprocessing / "cleaned_pages.jsonl",
        "preprocessing_summary": preprocessing / "preprocessing_summary.json",
        "legacy_chunks": pipeline / "chunk_metadata.jsonl",
        "legacy_embeddings": pipeline / "embeddings.npy",
        "legacy_index": pipeline / "faiss.index",
        "pipeline_config": pipeline / "pipeline_config.json",
        "gold_questions": evaluation / "gold_questions.jsonl",
        "evaluation_results": evaluation / "retrieval_results.jsonl",
        "selected_config": benchmark / "selected_config.json",
    }
    for path in paths.values():
        _require_file(path)
    checksums = {
        name: sha256_file(path) for name, path in paths.items() if name not in {"legacy_embeddings"}
    }
    checksums["legacy_embeddings"] = sha256_file(paths["legacy_embeddings"])

    documents: list[InventoryRecord] = []
    inventory_fields = {
        "document_id",
        "file_name",
        "file_type",
        "domain",
        "relative_path",
        "size_bytes",
        "ingested_at_utc",
    }
    with paths["inventory"].open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not inventory_fields <= set(reader.fieldnames):
            raise ArtifactValidationError("Document inventory schema is incomplete.")
        for row in reader:
            source_path = _safe_source(corpus_root, row["relative_path"])
            size_bytes = int(row["size_bytes"])
            if source_path.stat().st_size != size_bytes:
                raise ArtifactValidationError(f"Source size changed: {row['relative_path']}")
            documents.append(
                InventoryRecord(
                    legacy_document_id=row["document_id"],
                    file_name=row["file_name"],
                    file_type=row["file_type"].lower(),
                    domain=row["domain"],
                    relative_path=row["relative_path"],
                    source_path=source_path,
                    size_bytes=size_bytes,
                    ingested_at=datetime.fromisoformat(row["ingested_at_utc"]),
                    sha256=sha256_file(source_path),
                )
            )
    if len({row.legacy_document_id for row in documents}) != len(documents):
        raise ArtifactValidationError("Document inventory IDs are not unique.")
    if len({row.relative_path for row in documents}) != len(documents):
        raise ArtifactValidationError("Document inventory paths are not unique.")

    page_fields = {
        "document_id",
        "file_name",
        "domain",
        "file_type",
        "relative_path",
        "page_number",
        "raw_text",
    }
    extracted_rows = _read_jsonl(paths["extracted_pages"], page_fields)
    cleaned_rows = _read_jsonl(paths["cleaned_pages"], page_fields | {"cleaned_text"})
    _unique(extracted_rows, ("document_id", "page_number"), "extracted page")
    _unique(cleaned_rows, ("document_id", "page_number"), "cleaned page")
    extracted_keys = {(row["document_id"], int(row["page_number"])) for row in extracted_rows}
    cleaned_keys = {(row["document_id"], int(row["page_number"])) for row in cleaned_rows}
    if extracted_keys != cleaned_keys:
        raise ArtifactValidationError("Extracted and cleaned page identities do not match.")
    inventory_by_id = {row.legacy_document_id: row for row in documents}
    pages: list[PageRecord] = []
    for row in cleaned_rows:
        document = inventory_by_id.get(str(row["document_id"]))
        if document is None:
            raise ArtifactValidationError("A page references an unknown document.")
        if (
            row["file_name"] != document.file_name
            or row["relative_path"] != document.relative_path
            or row["domain"] != document.domain
        ):
            raise ArtifactValidationError("Page metadata does not match the inventory.")
        pages.append(
            PageRecord(
                legacy_document_id=document.legacy_document_id,
                file_name=document.file_name,
                domain=document.domain,
                file_type=document.file_type,
                relative_path=document.relative_path,
                page_number=int(row["page_number"]),
                raw_text=str(row["raw_text"]),
                cleaned_text=str(row["cleaned_text"]),
                repeated_lines_removed_count=int(row.get("repeated_lines_removed") or 0),
            )
        )

    summary = _read_json(paths["preprocessing_summary"])
    if int(summary.get("documents_processed", -1)) != len(documents):
        raise ArtifactValidationError("Inventory count differs from preprocessing summary.")
    if int(summary.get("extracted_pages", -1)) != len(pages):
        raise ArtifactValidationError("Page count differs from preprocessing summary.")

    legacy_chunks = _read_jsonl(
        paths["legacy_chunks"],
        {"chunk_id", "document_id", "page_number", "chunk_index", "cleaned_text"},
    )
    _unique(legacy_chunks, ("chunk_id",), "legacy chunk")
    pipeline_config = _read_json(paths["pipeline_config"])
    legacy_count = int(pipeline_config.get("chunk_count", -1))
    legacy_dimension = int(pipeline_config.get("embedding_dimension", -1))
    if legacy_count != len(legacy_chunks):
        raise ArtifactValidationError("Legacy chunk count differs from pipeline configuration.")
    if validate_legacy_vectors:
        _validate_legacy_vectors(pipeline, legacy_count, legacy_dimension)

    selected = _read_json(paths["selected_config"])
    selected_embedding = selected.get("embedding", {})
    selected_chunking = selected.get("chunking", {})
    selected_benchmark = selected.get("benchmark", {})
    expected_policy = (
        selected_embedding.get("model"),
        selected_embedding.get("revision"),
        selected_embedding.get("dimension"),
        selected_embedding.get("effective_max_tokens"),
        selected_chunking.get("version"),
        selected_chunking.get("target_content_tokens"),
        selected_chunking.get("maximum_content_tokens"),
        selected_chunking.get("overlap_content_tokens"),
    )
    configured_policy = (
        settings.embedding_model,
        settings.embedding_revision,
        settings.embedding_dimension,
        settings.embedding_max_input_tokens,
        settings.chunking_version,
        settings.chunk_target_tokens,
        settings.chunk_max_tokens,
        settings.chunk_overlap_tokens,
    )
    if expected_policy != configured_policy:
        raise ArtifactValidationError("Selected benchmark policy does not match backend settings.")
    if selected.get("compatibility", {}).get("existing_pipeline_artifacts_compatible") is not False:
        raise ArtifactValidationError("Expected the saved legacy index to be marked incompatible.")

    gold = _read_jsonl(
        paths["gold_questions"],
        {"evaluation_id", "domain", "question", "answerable", "supporting_document"},
    )
    evaluations = _read_jsonl(
        paths["evaluation_results"],
        {"evaluation_id", "domain", "question", "answerable", "retrieval_seconds"},
    )
    _unique(gold, ("evaluation_id",), "gold question")
    _unique(evaluations, ("evaluation_id",), "evaluation result")
    if {row["evaluation_id"] for row in gold} != {row["evaluation_id"] for row in evaluations}:
        raise ArtifactValidationError("Gold and evaluation result identities do not match.")
    file_names = {row.file_name for row in documents}
    for row in gold:
        if row["answerable"] and row.get("supporting_document") not in file_names:
            raise ArtifactValidationError("An answerable gold question has no source document.")
    gold_sha = sha256_file(paths["gold_questions"])
    if selected_benchmark.get("gold_dataset_sha256") != gold_sha:
        raise ArtifactValidationError("Gold dataset checksum differs from the accepted benchmark.")

    return ArtifactBundle(
        documents=tuple(documents),
        pages=tuple(pages),
        gold_questions=tuple(gold),
        evaluation_results=tuple(evaluations),
        checksums=checksums,
        legacy_chunk_count=legacy_count,
        legacy_dimension=legacy_dimension,
        selected_chunk_count=int(selected_benchmark["chunks"]),
        gold_dataset_sha256=gold_sha,
    )
