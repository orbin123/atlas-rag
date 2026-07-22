from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "experiments" / "calibrate_insufficient_context.py"
)
SPEC = importlib.util.spec_from_file_location("insufficient_context_calibration", MODULE_PATH)
assert SPEC and SPEC.loader
calibration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calibration
SPEC.loader.exec_module(calibration)


def sample_rows() -> list[dict[str, object]]:
    return [
        {"evaluation_id": "a1", "answerable": True, "top_score": 0.48},
        {"evaluation_id": "a2", "answerable": True, "top_score": 0.75},
        {"evaluation_id": "u1", "answerable": False, "top_score": 0.44},
    ]


class ConfusionMetricTests(unittest.TestCase):
    def test_threshold_is_inclusive_for_generation_eligibility(self) -> None:
        rows = [
            {"evaluation_id": "a", "answerable": True, "top_score": 0.46},
            {"evaluation_id": "u", "answerable": False, "top_score": 0.45},
        ]

        metrics = calibration.confusion_metrics(rows, 0.46)

        self.assertEqual(metrics["true_positive_answerable_eligible"], 1)
        self.assertEqual(metrics["true_negative_unsupported_refused"], 1)
        self.assertEqual(metrics["false_positive_unsupported_eligible"], 0)
        self.assertEqual(metrics["false_negative_answerable_refused"], 0)

    def test_reference_thresholds_expose_both_safety_failure_modes(self) -> None:
        rows = sample_rows()

        low = calibration.confusion_metrics(rows, 0.30)
        high = calibration.confusion_metrics(rows, 0.72)

        self.assertEqual(low["false_positive_unsupported_eligible"], 1)
        self.assertEqual(high["false_negative_answerable_refused"], 1)


class SelectionTests(unittest.TestCase):
    def test_selects_rounded_midpoint_inside_zero_error_gap(self) -> None:
        selection = calibration.select_threshold(sample_rows())

        self.assertEqual(selection["threshold"], 0.46)
        self.assertAlmostEqual(selection["maximum_unsupported_score"], 0.44)
        self.assertAlmostEqual(selection["minimum_answerable_score"], 0.48)

    def test_overlapping_distributions_require_explicit_tradeoff(self) -> None:
        rows = sample_rows()
        rows[0]["top_score"] = 0.43

        with self.assertRaisesRegex(ValueError, "zero-error top-score separation"):
            calibration.select_threshold(rows)


class InputValidationTests(unittest.TestCase):
    def test_selected_rows_reject_duplicate_evaluation_ids(self) -> None:
        records = [
            {
                "config": "minilm",
                "evaluation_id": "same",
                "answerable": True,
                "top_score": 0.5,
            },
            {
                "config": "minilm",
                "evaluation_id": "same",
                "answerable": False,
                "top_score": 0.4,
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in records))

            with self.assertRaisesRegex(ValueError, "duplicate evaluation IDs"):
                calibration.load_selected_rows(
                    path,
                    expected_answerable=1,
                    expected_unsupported=1,
                )

    def test_gold_alignment_detects_changed_labels(self) -> None:
        rows = sample_rows()
        gold = [
            {"evaluation_id": row["evaluation_id"], "answerable": not row["answerable"]}
            for row in rows
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "gold.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in gold))

            with self.assertRaisesRegex(ValueError, "changed_labels"):
                calibration.validate_gold_alignment(rows, path)


if __name__ == "__main__":
    unittest.main()
