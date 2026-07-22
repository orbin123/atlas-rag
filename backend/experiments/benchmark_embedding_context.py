#!/usr/bin/env python3
"""Benchmark tokenizer-safe embedding choices against the Atlas gold set.

This is an experiment, not request-time backend code. It rebuilds page-aware chunks
from the saved cleaned-page records, embeds them without truncation, evaluates the
saved gold questions, and writes reproducible JSON artifacts for the Phase 0 model
decision.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import re
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import faiss
import numpy as np
import sentence_transformers
import torch
import transformers
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAGES_PATH = PROJECT_ROOT / "artifacts" / "preprocessing" / "cleaned_pages.jsonl"
DEFAULT_GOLD_PATH = PROJECT_ROOT / "artifacts" / "evaluation" / "gold_questions.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "benchmarks" / "embedding_context"
K_VALUES = (1, 3, 5, 10)
FETCH_MULTIPLIER = 4
DUPLICATE_SIMILARITY_THRESHOLD = 0.97


@dataclass(frozen=True)
class BenchmarkConfig:
    key: str
    model_name: str
    revision: str
    effective_max_tokens: int
    chunk_target_tokens: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    document_prefix: str = ""
    query_prefix: str = ""
    trust_remote_code: bool = False
    batch_size: int = 32


CONFIGS = {
    "minilm": BenchmarkConfig(
        key="minilm",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        effective_max_tokens=256,
        chunk_target_tokens=220,
        chunk_max_tokens=240,
        chunk_overlap_tokens=60,
        batch_size=32,
    ),
    "nomic": BenchmarkConfig(
        key="nomic",
        model_name="nomic-ai/nomic-embed-text-v1.5",
        revision="e9b6763023c676ca8431644204f50c2b100d9aab",
        effective_max_tokens=8192,
        chunk_target_tokens=550,
        chunk_max_tokens=700,
        chunk_overlap_tokens=90,
        document_prefix="search_document: ",
        query_prefix="search_query: ",
        trust_remote_code=False,
        batch_size=8,
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile for an empty sequence.")
    return float(np.percentile(np.asarray(values, dtype=np.float64), quantile))


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def atomic_write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def encode_content(tokenizer: Any, text: str) -> list[int]:
    return list(tokenizer.encode(text, add_special_tokens=False, truncation=False))


def input_token_count(tokenizer: Any, text: str) -> int:
    encoded = tokenizer(
        text,
        add_special_tokens=True,
        truncation=False,
        return_attention_mask=False,
    )
    return len(encoded["input_ids"])


def split_text_units(text: str, tokenizer: Any, max_tokens: int) -> list[str]:
    """Split text at paragraph/sentence boundaries, then hard-split long sentences."""
    units: list[str] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

    for paragraph in paragraphs:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if sentence.strip()
        ]
        if not sentences:
            sentences = [paragraph]

        for sentence in sentences:
            token_ids = encode_content(tokenizer, sentence)
            if len(token_ids) <= max_tokens:
                units.append(sentence)
                continue
            remaining = token_ids
            while remaining:
                low = 1
                high = min(max_tokens, len(remaining))
                accepted_size = 0
                accepted_text = ""
                while low <= high:
                    middle = (low + high) // 2
                    decoded = tokenizer.decode(
                        remaining[:middle],
                        skip_special_tokens=True,
                    ).strip()
                    decoded_count = len(encode_content(tokenizer, decoded)) if decoded else 0
                    if decoded and decoded_count <= max_tokens:
                        accepted_size = middle
                        accepted_text = decoded
                        low = middle + 1
                    else:
                        high = middle - 1
                if not accepted_size:
                    raise AssertionError("Tokenizer could not produce a safe non-empty text unit.")
                units.append(accepted_text)
                remaining = remaining[accepted_size:]
    return units


def joined_token_count(tokenizer: Any, units: Sequence[str]) -> int:
    return len(encode_content(tokenizer, "\n\n".join(units)))


def overlap_units(
    tokenizer: Any,
    units: Sequence[str],
    overlap_tokens: int,
) -> tuple[list[str], int]:
    selected: list[str] = []

    for unit in reversed(units):
        candidate = [unit, *selected]
        candidate_count = joined_token_count(tokenizer, candidate)
        if candidate_count <= overlap_tokens:
            selected = candidate
            continue
        if not selected:
            token_ids = encode_content(tokenizer, unit)
            tail = tokenizer.decode(
                token_ids[-overlap_tokens:],
                skip_special_tokens=True,
            ).strip()
            if tail:
                selected = [tail]
        break

    return selected, joined_token_count(tokenizer, selected) if selected else 0


def chunk_pages(
    pages: Sequence[dict[str, Any]],
    tokenizer: Any,
    config: BenchmarkConfig,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    document_chunk_indexes: dict[str, int] = {}

    for page in pages:
        cleaned_text = str(page.get("cleaned_text") or "").strip()
        if not cleaned_text:
            continue
        units = split_text_units(cleaned_text, tokenizer, config.chunk_max_tokens)
        pending: list[str] = []
        pending_overlap = 0
        page_chunks: list[tuple[list[str], int]] = []

        def flush() -> None:
            nonlocal pending, pending_overlap
            if pending:
                page_chunks.append((pending, pending_overlap))

        for unit in units:
            candidate = [*pending, unit]
            current_count = joined_token_count(tokenizer, pending) if pending else 0
            candidate_count = joined_token_count(tokenizer, candidate)
            if pending and (
                current_count >= config.chunk_target_tokens
                or candidate_count > config.chunk_max_tokens
            ):
                previous = pending
                flush()
                pending, pending_overlap = overlap_units(
                    tokenizer,
                    previous,
                    config.chunk_overlap_tokens,
                )
                while pending and joined_token_count(tokenizer, [*pending, unit]) > config.chunk_max_tokens:
                    pending = pending[1:]
                    pending_overlap = joined_token_count(tokenizer, pending) if pending else 0
            pending.append(unit)

        flush()

        for page_ordinal, (chunk_units, overlap_count) in enumerate(page_chunks, start=1):
            text = "\n\n".join(chunk_units).strip()
            if not text:
                continue
            content_tokens = len(encode_content(tokenizer, text))
            if content_tokens > config.chunk_max_tokens:
                raise AssertionError(
                    f"Chunk exceeded configured content maximum: {content_tokens} > "
                    f"{config.chunk_max_tokens}"
                )
            model_input_tokens = input_token_count(tokenizer, f"{config.document_prefix}{text}")
            if model_input_tokens > config.effective_max_tokens:
                raise AssertionError(
                    f"Chunk would be truncated: {model_input_tokens} > "
                    f"{config.effective_max_tokens}"
                )

            document_id = str(page["document_id"])
            chunk_index = document_chunk_indexes.get(document_id, 0) + 1
            document_chunk_indexes[document_id] = chunk_index
            identity = (
                f"{config.key}:{document_id}:{page['page_number']}:{page_ordinal}:{text}"
            ).encode("utf-8")
            chunks.append(
                {
                    "chunk_id": f"bench_{hashlib.sha256(identity).hexdigest()[:20]}",
                    "document_id": document_id,
                    "file_name": page["file_name"],
                    "domain": page["domain"],
                    "page_number": int(page["page_number"]),
                    "chunk_index": chunk_index,
                    "cleaned_text": text,
                    "content_token_count": content_tokens,
                    "model_input_token_count": model_input_tokens,
                    "overlap_from_previous_tokens": overlap_count,
                }
            )
    return chunks


def first_relevant_rank(
    results: Sequence[dict[str, Any]],
    supporting_document: str | None,
    supporting_page: int | None,
) -> int | None:
    if supporting_document is None:
        return None
    for result in results:
        file_matches = result["file_name"] == supporting_document
        page_matches = supporting_page is None or result["page_number"] == int(supporting_page)
        if file_matches and page_matches:
            return int(result["rank"])
    return None


def compute_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float | int]:
    answerable = [row for row in rows if row["answerable"]]
    if not answerable:
        raise ValueError("The benchmark requires at least one answerable question.")
    metrics: dict[str, float | int] = {
        "questions": len(rows),
        "answerable_questions": len(answerable),
        "unsupported_questions": len(rows) - len(answerable),
    }
    for k in K_VALUES:
        metrics[f"recall_at_{k}"] = sum(
            bool(row["first_relevant_rank"] and row["first_relevant_rank"] <= k)
            for row in answerable
        ) / len(answerable)
    metrics["mrr"] = sum(
        1.0 / row["first_relevant_rank"] if row["first_relevant_rank"] else 0.0
        for row in answerable
    ) / len(answerable)
    return metrics


def retrieve(
    question_vector: np.ndarray,
    index: faiss.Index,
    embeddings: np.ndarray,
    chunks: Sequence[dict[str, Any]],
    k: int = 10,
) -> list[dict[str, Any]]:
    fetch_k = min(index.ntotal, max(k, k * FETCH_MULTIPLIER))
    scores, positions = index.search(question_vector, fetch_k)
    kept_positions: list[int] = []
    results: list[dict[str, Any]] = []

    for score, position in zip(scores[0], positions[0], strict=True):
        if position < 0:
            continue
        position = int(position)
        if kept_positions:
            similarities = embeddings[kept_positions] @ embeddings[position]
            if float(similarities.max()) >= DUPLICATE_SIMILARITY_THRESHOLD:
                continue
        chunk = chunks[position]
        results.append(
            {
                "rank": len(results) + 1,
                "score": float(score),
                "chunk_id": chunk["chunk_id"],
                "file_name": chunk["file_name"],
                "domain": chunk["domain"],
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
            }
        )
        kept_positions.append(position)
        if len(results) == k:
            break
    return results


def describe_numbers(values: Sequence[int | float]) -> dict[str, float | int]:
    if not values:
        return {"minimum": 0, "maximum": 0, "mean": 0.0, "median": 0.0, "p95": 0.0}
    return {
        "minimum": min(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": percentile([float(value) for value in values], 95),
    }


def benchmark_config(
    config: BenchmarkConfig,
    pages: Sequence[dict[str, Any]],
    gold: Sequence[dict[str, Any]],
    device: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    load_started = time.perf_counter()
    model = SentenceTransformer(
        config.model_name,
        revision=config.revision,
        trust_remote_code=config.trust_remote_code,
        device=device,
    )
    model.max_seq_length = config.effective_max_tokens
    model_load_seconds = time.perf_counter() - load_started
    tokenizer = model.tokenizer

    chunk_started = time.perf_counter()
    chunks = chunk_pages(pages, tokenizer, config)
    chunking_seconds = time.perf_counter() - chunk_started
    if not chunks:
        raise AssertionError("Chunking produced no records.")

    document_inputs = [f"{config.document_prefix}{chunk['cleaned_text']}" for chunk in chunks]
    embedding_started = time.perf_counter()
    embeddings = model.encode(
        document_inputs,
        batch_size=config.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32", copy=False)
    embedding_seconds = time.perf_counter() - embedding_started
    if embeddings.shape[0] != len(chunks):
        raise AssertionError("Embedding rows do not align with chunks.")
    if not np.isfinite(embeddings).all():
        raise AssertionError("Embeddings contain non-finite values.")
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        raise AssertionError("Embeddings are not L2-normalized.")

    index_started = time.perf_counter()
    index = faiss.IndexFlatIP(int(embeddings.shape[1]))
    index.add(embeddings)
    index_build_seconds = time.perf_counter() - index_started
    if index.ntotal != len(chunks):
        raise AssertionError("FAISS index count does not align with chunks.")

    # Warm model and search kernels before timing the gold set.
    warm_query = model.encode(
        [f"{config.query_prefix}{gold[0]['question']}"],
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32", copy=False)
    retrieve(warm_query, index, embeddings, chunks)

    evaluation_rows: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for record in gold:
        retrieval_started = time.perf_counter()
        question_vector = model.encode(
            [f"{config.query_prefix}{record['question']}"],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32", copy=False)
        results = retrieve(question_vector, index, embeddings, chunks)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        latencies_ms.append(retrieval_ms)
        rank = (
            first_relevant_rank(
                results,
                record.get("supporting_document"),
                record.get("supporting_page"),
            )
            if record["answerable"]
            else None
        )
        evaluation_rows.append(
            {
                "config": config.key,
                "evaluation_id": record["evaluation_id"],
                "domain": record["domain"],
                "question": record["question"],
                "answerable": bool(record["answerable"]),
                "supporting_document": record.get("supporting_document"),
                "supporting_page": record.get("supporting_page"),
                "first_relevant_rank": rank,
                "reciprocal_rank": 1.0 / rank if rank else 0.0,
                "top_score": results[0]["score"] if results else None,
                "top_file_name": results[0]["file_name"] if results else None,
                "retrieval_ms": retrieval_ms,
                "results": results,
            }
        )

    serialized_index = faiss.serialize_index(index)
    content_counts = [int(chunk["content_token_count"]) for chunk in chunks]
    input_counts = [int(chunk["model_input_token_count"]) for chunk in chunks]
    overlap_counts = [
        int(chunk["overlap_from_previous_tokens"])
        for chunk in chunks
        if chunk["overlap_from_previous_tokens"] > 0
    ]
    metrics = compute_metrics(evaluation_rows)
    metrics.update(
        {
            "retrieval_mean_ms": statistics.fmean(latencies_ms),
            "retrieval_median_ms": statistics.median(latencies_ms),
            "retrieval_p95_ms": percentile(latencies_ms, 95),
        }
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    tokenizer_max = int(getattr(tokenizer, "model_max_length", config.effective_max_tokens))
    summary = {
        "config": asdict(config),
        "runtime": {
            "device": str(model.device),
            "torch_dtype": str(next(model.parameters()).dtype),
            "model_load_seconds": model_load_seconds,
            "chunking_seconds": chunking_seconds,
            "embedding_seconds": embedding_seconds,
            "embedding_ms_per_chunk": embedding_seconds * 1000 / len(chunks),
            "index_build_seconds": index_build_seconds,
        },
        "model": {
            "sentence_transformer_max_seq_length": int(model.max_seq_length),
            "tokenizer_model_max_length": tokenizer_max,
            "tokenizer_class": type(tokenizer).__name__,
            "embedding_dimension": int(embeddings.shape[1]),
            "parameter_count": int(parameter_count),
            "normalization": "L2 float32",
        },
        "chunks": {
            "count": len(chunks),
            "documents": len({chunk["document_id"] for chunk in chunks}),
            "content_tokens": describe_numbers(content_counts),
            "model_input_tokens": describe_numbers(input_counts),
            "overlap_tokens_when_present": describe_numbers(overlap_counts),
            "chunks_above_effective_model_limit": sum(
                count > config.effective_max_tokens for count in input_counts
            ),
        },
        "storage": {
            "embedding_bytes": int(embeddings.nbytes),
            "serialized_flat_ip_index_bytes": int(serialized_index.nbytes),
        },
        "retrieval": metrics,
    }

    del model, tokenizer, embeddings, index, serialized_index
    gc.collect()
    return summary, evaluation_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=sorted(CONFIGS),
        default=list(CONFIGS),
        help="Benchmark configurations to run in order.",
    )
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES_PATH)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--merge-inputs",
        nargs="+",
        type=Path,
        help="Merge completed single-model output directories without rerunning models.",
    )
    return parser.parse_args()


def merge_outputs(input_dirs: Sequence[Path], output_dir: Path) -> None:
    if len(input_dirs) < 2:
        raise ValueError("Merging requires at least two completed benchmark directories.")
    summaries = [json.loads((directory / "summary.json").read_text()) for directory in input_dirs]
    reference = summaries[0]
    for summary in summaries[1:]:
        for key in ("benchmark_version", "inputs", "environment", "retrieval_config"):
            if summary[key] != reference[key]:
                raise ValueError(f"Cannot merge benchmarks with different {key} values.")

    results = [result for summary in summaries for result in summary["results"]]
    config_keys = [result["config"]["key"] for result in results]
    if len(config_keys) != len(set(config_keys)):
        raise ValueError("Cannot merge duplicate benchmark configurations.")
    rows = [
        record
        for directory in input_dirs
        for record in load_jsonl(directory / "retrieval_results.jsonl")
    ]
    expected_rows = int(reference["inputs"]["gold_questions"]) * len(results)
    if len(rows) != expected_rows:
        raise ValueError(f"Expected {expected_rows} retrieval rows, found {len(rows)}.")

    merged = {
        "benchmark_version": reference["benchmark_version"],
        "started_at_utc": min(summary["started_at_utc"] for summary in summaries),
        "completed_at_utc": max(summary["completed_at_utc"] for summary in summaries),
        "inputs": reference["inputs"],
        "environment": reference["environment"],
        "retrieval_config": reference["retrieval_config"],
        "results": results,
    }
    atomic_write_json(output_dir / "summary.json", merged)
    atomic_write_jsonl(output_dir / "retrieval_results.jsonl", rows)
    print(f"Merged benchmark results into {output_dir}", flush=True)


def main() -> None:
    args = parse_args()
    if args.merge_inputs:
        merge_outputs(args.merge_inputs, args.output_dir)
        return
    pages = load_jsonl(args.pages)
    gold = load_jsonl(args.gold)
    if len(pages) != 1848:
        raise ValueError(f"Expected 1,848 cleaned pages, found {len(pages):,}.")
    if len(gold) != 33:
        raise ValueError(f"Expected 33 gold questions, found {len(gold):,}.")
    if sum(bool(record["answerable"]) for record in gold) != 30:
        raise ValueError("Expected 30 answerable gold questions.")

    started_at = utc_now()
    summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for key in args.models:
        print(f"\nBenchmarking {key}: {CONFIGS[key].model_name}", flush=True)
        summary, rows = benchmark_config(CONFIGS[key], pages, gold, args.device)
        summaries.append(summary)
        all_rows.extend(rows)
        print(
            json.dumps(
                {
                    "config": key,
                    "chunks": summary["chunks"]["count"],
                    "recall_at_5": summary["retrieval"]["recall_at_5"],
                    "mrr": summary["retrieval"]["mrr"],
                    "embedding_seconds": summary["runtime"]["embedding_seconds"],
                },
                indent=2,
            ),
            flush=True,
        )

    output = {
        "benchmark_version": 1,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "inputs": {
            "cleaned_pages_path": str(args.pages.relative_to(PROJECT_ROOT)),
            "cleaned_pages_sha256": sha256_file(args.pages),
            "gold_path": str(args.gold.relative_to(PROJECT_ROOT)),
            "gold_sha256": sha256_file(args.gold),
            "page_records": len(pages),
            "gold_questions": len(gold),
            "answerable_questions": sum(bool(record["answerable"]) for record in gold),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "sentence_transformers": sentence_transformers.__version__,
            "numpy": np.__version__,
            "faiss": faiss.__version__,
            "requested_device": args.device,
        },
        "retrieval_config": {
            "k_values": list(K_VALUES),
            "fetch_multiplier": FETCH_MULTIPLIER,
            "duplicate_similarity_threshold": DUPLICATE_SIMILARITY_THRESHOLD,
        },
        "results": summaries,
    }
    atomic_write_json(args.output_dir / "summary.json", output)
    atomic_write_jsonl(args.output_dir / "retrieval_results.jsonl", all_rows)
    print(f"\nWrote benchmark results to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
