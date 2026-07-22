from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "experiments" / "benchmark_embedding_context.py"
)
SPEC = importlib.util.spec_from_file_location("embedding_context_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class WordTokenizer:
    model_max_length = 100

    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._words: dict[int, str] = {}

    def encode(
        self,
        text: str,
        add_special_tokens: bool = False,
        truncation: bool = False,
    ) -> list[int]:
        del truncation
        ids = []
        for word in text.split():
            if word not in self._ids:
                identifier = len(self._ids) + 10
                self._ids[word] = identifier
                self._words[identifier] = word
            ids.append(self._ids[word])
        return ([1, *ids, 2] if add_special_tokens else ids)

    def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        return " ".join(self._words[token_id] for token_id in token_ids)

    def __call__(self, text: str, **_: object) -> dict[str, list[int]]:
        return {"input_ids": self.encode(text, add_special_tokens=True)}


class ChunkingTests(unittest.TestCase):
    def test_chunks_never_exceed_content_or_effective_model_limit(self) -> None:
        tokenizer = WordTokenizer()
        config = benchmark.BenchmarkConfig(
            key="test",
            model_name="test",
            revision="test",
            effective_max_tokens=14,
            chunk_target_tokens=8,
            chunk_max_tokens=10,
            chunk_overlap_tokens=3,
            document_prefix="doc ",
        )
        page = {
            "document_id": "doc-1",
            "file_name": "example.txt",
            "domain": "Test",
            "page_number": 1,
            "cleaned_text": (
                "one two three four. five six seven eight. "
                "nine ten eleven twelve. thirteen fourteen fifteen sixteen."
            ),
        }

        chunks = benchmark.chunk_pages([page], tokenizer, config)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(
            all(chunk["content_token_count"] <= config.chunk_max_tokens for chunk in chunks)
        )
        self.assertTrue(
            all(
                chunk["model_input_token_count"] <= config.effective_max_tokens
                for chunk in chunks
            )
        )
        self.assertTrue(any(chunk["overlap_from_previous_tokens"] for chunk in chunks[1:]))

    def test_hard_split_recounts_decoded_text(self) -> None:
        class ExpandingDecodeTokenizer(WordTokenizer):
            def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
                decoded = super().decode(token_ids, skip_special_tokens)
                return f"{decoded} expansion"

        tokenizer = ExpandingDecodeTokenizer()
        token_ids = tokenizer.encode("one two three four five six", add_special_tokens=False)
        text = tokenizer.decode(token_ids)

        units = benchmark.split_text_units(text, tokenizer, max_tokens=4)

        self.assertGreater(len(units), 1)
        self.assertTrue(all(len(tokenizer.encode(unit)) <= 4 for unit in units))


class MetricTests(unittest.TestCase):
    def test_metrics_exclude_unsupported_questions(self) -> None:
        rows = [
            {"answerable": True, "first_relevant_rank": 1},
            {"answerable": True, "first_relevant_rank": 4},
            {"answerable": True, "first_relevant_rank": None},
            {"answerable": False, "first_relevant_rank": None},
        ]

        metrics = benchmark.compute_metrics(rows)

        self.assertEqual(metrics["answerable_questions"], 3)
        self.assertEqual(metrics["unsupported_questions"], 1)
        self.assertAlmostEqual(metrics["recall_at_1"], 1 / 3)
        self.assertAlmostEqual(metrics["recall_at_5"], 2 / 3)
        self.assertAlmostEqual(metrics["mrr"], (1 + 0.25) / 3)


class MergeTests(unittest.TestCase):
    def test_merge_preserves_both_results_and_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directories = [root / "one", root / "two"]
            for index, directory in enumerate(input_directories, start=1):
                directory.mkdir()
                summary = {
                    "benchmark_version": 1,
                    "started_at_utc": f"2026-01-0{index}T00:00:00+00:00",
                    "completed_at_utc": f"2026-01-0{index}T01:00:00+00:00",
                    "inputs": {"gold_questions": 1},
                    "environment": {"device": "test"},
                    "retrieval_config": {"k_values": [1]},
                    "results": [{"config": {"key": f"model-{index}"}}],
                }
                (directory / "summary.json").write_text(json.dumps(summary))
                (directory / "retrieval_results.jsonl").write_text(
                    json.dumps({"config": f"model-{index}"}) + "\n"
                )

            output_directory = root / "merged"
            benchmark.merge_outputs(input_directories, output_directory)

            merged = json.loads((output_directory / "summary.json").read_text())
            rows = benchmark.load_jsonl(output_directory / "retrieval_results.jsonl")
            self.assertEqual(len(merged["results"]), 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(merged["started_at_utc"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(merged["completed_at_utc"], "2026-01-02T01:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
