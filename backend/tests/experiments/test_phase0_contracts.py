from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "experiments/verify_phase0_contracts.py"
SPEC = importlib.util.spec_from_file_location("phase0_contract_verifier", MODULE_PATH)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)

API_CONTRACT_PATH = verifier.API_CONTRACT_PATH
GENERATION_POLICY_PATH = verifier.GENERATION_POLICY_PATH
ROOT = verifier.ROOT
load_json = verifier.load_json
policy_outcome = verifier.policy_outcome
validate_api_contract = verifier.validate_api_contract
validate_generation_policy = verifier.validate_generation_policy
verify = verifier.verify


class PhaseZeroContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api_contract = load_json(API_CONTRACT_PATH)
        cls.generation_policy = load_json(GENERATION_POLICY_PATH)

    def test_complete_phase_zero_contracts_verify(self) -> None:
        result = verify()
        self.assertEqual(result["operations"], 20)
        self.assertEqual(result["frontendComponents"], 6)
        self.assertEqual(result["mockReplacements"], 12)
        self.assertEqual(result["minimumContextScore"], 0.46)

    def test_retrieval_only_readiness_is_valid(self) -> None:
        validate_generation_policy(self.generation_policy)
        readiness = self.generation_policy["readiness"]
        self.assertTrue(readiness["retrievalReadyWhenGenerationDisabled"])
        self.assertFalse(readiness["generationReadyWhenDisabled"])

    def test_below_threshold_never_calls_provider(self) -> None:
        result = policy_outcome(
            top_score=0.459999,
            threshold=0.46,
            provider_ready=True,
        )
        self.assertEqual(result, (200, "insufficient_context", None, False))

    def test_threshold_is_inclusive_and_unconfigured_provider_is_typed(self) -> None:
        result = policy_outcome(
            top_score=0.46,
            threshold=0.46,
            provider_ready=False,
        )
        self.assertEqual(
            result,
            (503, "provider_unavailable", "GENERATION_PROVIDER_UNAVAILABLE", False),
        )

    def test_timeout_remains_distinct_from_insufficient_context(self) -> None:
        result = policy_outcome(
            top_score=0.7,
            threshold=0.46,
            provider_ready=True,
            provider_failure="timeout",
        )
        self.assertEqual(result, (504, "provider_error", "GENERATION_TIMEOUT", True))

    def test_unknown_frontend_operation_is_rejected(self) -> None:
        contract = deepcopy(self.api_contract)
        contract["frontendCoverage"]["frontend/src/App.tsx"].append("missing")
        with self.assertRaisesRegex(ValueError, "Unknown frontend operations"):
            validate_api_contract(contract)

    def test_duplicate_route_is_rejected(self) -> None:
        contract = deepcopy(self.api_contract)
        contract["operations"]["duplicate"] = deepcopy(
            contract["operations"]["getSystemInfo"]
        )
        with self.assertRaisesRegex(ValueError, "Duplicate method/path"):
            validate_api_contract(contract)

    def test_snake_case_response_field_is_rejected(self) -> None:
        contract = deepcopy(self.api_contract)
        contract["schemas"]["SystemInfoResponse"].append("bad_field")
        with self.assertRaisesRegex(ValueError, "camelCase"):
            validate_api_contract(contract)

    def test_missing_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative_path in self.api_contract["frontendCoverage"]:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            missing = root / "frontend/src/App.tsx"
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "component is missing"):
                validate_api_contract(self.api_contract, root)

    def test_contract_files_are_canonical_json(self) -> None:
        for path in (API_CONTRACT_PATH, GENERATION_POLICY_PATH):
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(parsed, dict)
            self.assertEqual(parsed["contractVersion"], "1.0.0")

    def test_paths_are_repository_relative(self) -> None:
        for path in (API_CONTRACT_PATH, GENERATION_POLICY_PATH):
            self.assertTrue(path.is_relative_to(ROOT))


if __name__ == "__main__":
    unittest.main()
