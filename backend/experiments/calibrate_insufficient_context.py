#!/usr/bin/env python3
"""Calibrate Atlas RAG's top-score insufficient-context threshold.

This Phase 0 experiment consumes the selected embedding benchmark's real retrieval
rows. It treats a query as generation-eligible when its top cosine-equivalent
score is greater than or equal to the threshold, prioritizes refusing every known
unsupported question, and retains as many answerable questions as possible.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RETRIEVAL_RESULTS = (
    PROJECT_ROOT
    / "artifacts"
    / "benchmarks"
    / "embedding_context"
    / "retrieval_results.jsonl"
)
DEFAULT_GOLD_DATASET = PROJECT_ROOT / "artifacts" / "evaluation" / "gold_questions.jsonl"
DEFAULT_SELECTED_CONFIG = (
    PROJECT_ROOT / "artifacts" / "benchmarks" / "embedding_context" / "selected_config.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "artifacts" / "benchmarks" / "insufficient_context_calibration"
)
CONFIG_KEY = "minilm"
EXPECTED_ANSWERABLE = 30
EXPECTED_UNSUPPORTED = 3
REFERENCE_THRESHOLDS = (0.30, 0.72)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


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
    path.chmod(0o644)


def atomic_write_csv(
    path: Path,
    rows: Iterable[dict[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)
    path.chmod(0o644)


def load_selected_rows(
    retrieval_results_path: Path,
    config_key: str = CONFIG_KEY,
    expected_answerable: int = EXPECTED_ANSWERABLE,
    expected_unsupported: int = EXPECTED_UNSUPPORTED,
) -> list[dict[str, Any]]:
    rows = [
        row for row in load_jsonl(retrieval_results_path) if row.get("config") == config_key
    ]
    evaluation_ids = [str(row.get("evaluation_id") or "") for row in rows]
    if not rows:
        raise ValueError(f"No retrieval rows found for configuration {config_key!r}.")
    if any(not evaluation_id for evaluation_id in evaluation_ids):
        raise ValueError("Every retrieval row must contain an evaluation_id.")
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError("Selected retrieval rows contain duplicate evaluation IDs.")

    for row in rows:
        score = row.get("top_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"Retrieval row {row['evaluation_id']} has no numeric top score.")
        if not math.isfinite(float(score)) or not -1.0 <= float(score) <= 1.0:
            raise ValueError(f"Retrieval row {row['evaluation_id']} has an invalid top score.")
        if not isinstance(row.get("answerable"), bool):
            raise ValueError(f"Retrieval row {row['evaluation_id']} has no boolean label.")

    answerable = sum(row["answerable"] for row in rows)
    unsupported = len(rows) - answerable
    if (answerable, unsupported) != (expected_answerable, expected_unsupported):
        raise ValueError(
            "Selected retrieval labels do not match the expected calibration set: "
            f"found {answerable} answerable and {unsupported} unsupported."
        )
    return rows


def validate_gold_alignment(rows: Sequence[dict[str, Any]], gold_path: Path) -> None:
    gold = load_jsonl(gold_path)
    gold_labels = {
        str(record["evaluation_id"]): bool(record["answerable"]) for record in gold
    }
    if len(gold_labels) != len(gold):
        raise ValueError("Gold dataset contains duplicate evaluation IDs.")
    row_labels = {str(row["evaluation_id"]): bool(row["answerable"]) for row in rows}
    if row_labels != gold_labels:
        missing = sorted(set(gold_labels) - set(row_labels))
        extra = sorted(set(row_labels) - set(gold_labels))
        changed = sorted(
            evaluation_id
            for evaluation_id in set(gold_labels) & set(row_labels)
            if gold_labels[evaluation_id] != row_labels[evaluation_id]
        )
        raise ValueError(
            "Retrieval rows do not align with the gold dataset "
            f"(missing={missing}, extra={extra}, changed_labels={changed})."
        )


def confusion_metrics(rows: Sequence[dict[str, Any]], threshold: float) -> dict[str, Any]:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be between 0 and 1.")
    true_positive = false_negative = true_negative = false_positive = 0
    for row in rows:
        generation_eligible = float(row["top_score"]) >= threshold
        if row["answerable"] and generation_eligible:
            true_positive += 1
        elif row["answerable"]:
            false_negative += 1
        elif generation_eligible:
            false_positive += 1
        else:
            true_negative += 1

    answerable_total = true_positive + false_negative
    unsupported_total = true_negative + false_positive
    eligible_total = true_positive + false_positive
    return {
        "threshold": threshold,
        "true_positive_answerable_eligible": true_positive,
        "false_negative_answerable_refused": false_negative,
        "true_negative_unsupported_refused": true_negative,
        "false_positive_unsupported_eligible": false_positive,
        "answerable_retention": true_positive / answerable_total,
        "unsupported_refusal_recall": true_negative / unsupported_total,
        "unsupported_false_acceptance_rate": false_positive / unsupported_total,
        "eligible_precision": true_positive / eligible_total if eligible_total else None,
        "balanced_accuracy": (
            (true_positive / answerable_total) + (true_negative / unsupported_total)
        )
        / 2,
    }


def select_threshold(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    answerable_scores = sorted(float(row["top_score"]) for row in rows if row["answerable"])
    unsupported_scores = sorted(
        float(row["top_score"]) for row in rows if not row["answerable"]
    )
    maximum_unsupported = unsupported_scores[-1]
    minimum_answerable = answerable_scores[0]
    if maximum_unsupported >= minimum_answerable:
        raise ValueError(
            "The current labels do not have a zero-error top-score separation; "
            "an explicit tradeoff decision is required."
        )

    midpoint = (maximum_unsupported + minimum_answerable) / 2
    rounded_midpoint = round(midpoint, 2)
    threshold = (
        rounded_midpoint
        if maximum_unsupported < rounded_midpoint <= minimum_answerable
        else midpoint
    )
    return {
        "threshold": threshold,
        "raw_gap_midpoint": midpoint,
        "maximum_unsupported_score": maximum_unsupported,
        "minimum_answerable_score": minimum_answerable,
        "observed_separation_gap": minimum_answerable - maximum_unsupported,
        "margin_above_maximum_unsupported": threshold - maximum_unsupported,
        "margin_below_minimum_answerable": minimum_answerable - threshold,
        "rounding": "two decimals when the rounded midpoint remains inside the zero-error gap",
    }


def describe_scores(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot describe an empty score distribution.")

    def nearest_rank(fraction: float) -> float:
        position = round((len(ordered) - 1) * fraction)
        return ordered[position]

    return {
        "minimum": ordered[0],
        "p25": nearest_rank(0.25),
        "median": statistics.median(ordered),
        "p75": nearest_rank(0.75),
        "maximum": ordered[-1],
        "mean": statistics.fmean(ordered),
    }


def candidate_thresholds(selected_threshold: float) -> list[float]:
    values = {round(step / 100, 2) for step in range(101)}
    values.update(REFERENCE_THRESHOLDS)
    values.add(selected_threshold)
    return sorted(values)


def write_distribution_plot(
    path: Path,
    rows: Sequence[dict[str, Any]],
    selected_threshold: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    answerable = sorted(float(row["top_score"]) for row in rows if row["answerable"])
    unsupported = sorted(float(row["top_score"]) for row in rows if not row["answerable"])
    figure, axis = plt.subplots(figsize=(10, 4.8))
    axis.scatter(
        answerable,
        [1] * len(answerable),
        color="#2563eb",
        label="Answerable (n=30)",
    )
    axis.scatter(
        unsupported,
        [0] * len(unsupported),
        color="#dc2626",
        marker="x",
        s=70,
        label="Unsupported (n=3)",
    )
    axis.axvline(0.30, color="#6b7280", linestyle=":", label="Prior pipeline 0.30")
    axis.axvline(
        selected_threshold,
        color="#059669",
        linewidth=2,
        label=f"Selected {selected_threshold:.2f}",
    )
    axis.axvline(0.72, color="#9333ea", linestyle="--", label="Prototype UI 0.72")
    axis.set(
        xlabel="Top normalized inner-product score",
        title="Atlas gold-set top-score distributions",
        xlim=(0.2, 0.85),
        yticks=[0, 1],
        yticklabels=["Unsupported", "Answerable"],
    )
    axis.grid(axis="x", alpha=0.2)
    axis.legend(loc="lower right", fontsize=8)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def build_summary(
    rows: Sequence[dict[str, Any]],
    retrieval_results_path: Path,
    gold_path: Path,
    selected_config_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected_config = json.loads(selected_config_path.read_text(encoding="utf-8"))
    expected_results_hash = selected_config["benchmark"]["retrieval_results_sha256"]
    actual_results_hash = sha256_file(retrieval_results_path)
    if expected_results_hash != actual_results_hash:
        raise ValueError("Retrieval results checksum does not match selected_config.json.")
    expected_gold_hash = selected_config["benchmark"]["gold_dataset_sha256"]
    actual_gold_hash = sha256_file(gold_path)
    if expected_gold_hash != actual_gold_hash:
        raise ValueError("Gold dataset checksum does not match selected_config.json.")

    selection = select_threshold(rows)
    selected_threshold = float(selection["threshold"])
    candidates = [
        confusion_metrics(rows, threshold)
        for threshold in candidate_thresholds(selected_threshold)
    ]
    comparisons = {
        f"{threshold:.2f}": confusion_metrics(rows, threshold)
        for threshold in (*REFERENCE_THRESHOLDS, selected_threshold)
    }
    answerable_scores = [float(row["top_score"]) for row in rows if row["answerable"]]
    unsupported_scores = [float(row["top_score"]) for row in rows if not row["answerable"]]
    summary = {
        "schema_version": 1,
        "calibrated_at_utc": utc_now(),
        "status": "accepted_with_limited_negative_sample",
        "classification_rule": {
            "generation_eligible": "top_score >= threshold",
            "insufficient_context": "top_score < threshold",
            "score": "cosine-equivalent inner product of L2-normalized MiniLM vectors",
        },
        "selection_objective": [
            "refuse every known unsupported question",
            "retain the maximum number of known answerable questions",
            "when the classes are separated, choose the rounded midpoint of the empirical gap",
        ],
        "selection": selection,
        "selected_metrics": confusion_metrics(rows, selected_threshold),
        "reference_comparisons": comparisons,
        "score_distributions": {
            "answerable": describe_scores(answerable_scores),
            "unsupported": describe_scores(unsupported_scores),
        },
        "dataset": {
            "retrieval_results_path": str(retrieval_results_path.relative_to(PROJECT_ROOT)),
            "retrieval_results_sha256": actual_results_hash,
            "gold_path": str(gold_path.relative_to(PROJECT_ROOT)),
            "gold_sha256": actual_gold_hash,
            "selected_config_path": str(selected_config_path.relative_to(PROJECT_ROOT)),
            "selected_config_sha256": sha256_file(selected_config_path),
            "config_key": CONFIG_KEY,
            "questions": len(rows),
            "answerable_questions": len(answerable_scores),
            "unsupported_questions": len(unsupported_scores),
        },
        "limitations": [
            (
                "Only three unsupported questions are available, so zero observed "
                "false acceptance is not a generalization guarantee."
            ),
            (
                "The threshold is coupled to this corpus, gold dataset, embedding/"
                "chunk schema, and top-score gate."
            ),
            (
                "Top-score eligibility does not prove that every retrieved source "
                "is relevant or that a generated answer is correct."
            ),
        ],
        "recalibration_triggers": [
            "gold dataset or corpus content changes",
            "embedding model, revision, prefixes, normalization, or chunking changes",
            "retrieval deduplication or score computation changes",
        ],
    }
    return summary, candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-results", type=Path, default=DEFAULT_RETRIEVAL_RESULTS)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_DATASET)
    parser.add_argument("--selected-config", type=Path, default=DEFAULT_SELECTED_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_selected_rows(args.retrieval_results)
    validate_gold_alignment(rows, args.gold)
    summary, candidates = build_summary(
        rows,
        args.retrieval_results,
        args.gold,
        args.selected_config,
    )
    output_dir = args.output_dir
    atomic_write_json(output_dir / "summary.json", summary)
    atomic_write_csv(
        output_dir / "candidate_metrics.csv",
        candidates,
        fieldnames=list(candidates[0]),
    )
    write_distribution_plot(
        output_dir / "score_distributions.png",
        rows,
        float(summary["selection"]["threshold"]),
    )
    print(
        json.dumps(
            {
                "threshold": summary["selection"]["threshold"],
                "selected_metrics": summary["selected_metrics"],
                "output_dir": str(output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
