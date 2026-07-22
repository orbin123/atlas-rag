#!/usr/bin/env python3
"""Verify the accepted Phase 0 API, model, threshold, and generation contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
API_CONTRACT_PATH = ROOT / "backend/contracts/api_v1.json"
GENERATION_POLICY_PATH = ROOT / "backend/contracts/generation_policy.json"
EMBEDDING_CONFIG_PATH = (
    ROOT / "artifacts/benchmarks/embedding_context/selected_config.json"
)
THRESHOLD_SUMMARY_PATH = (
    ROOT / "artifacts/benchmarks/insufficient_context_calibration/summary.json"
)

CAMEL_CASE = re.compile(r"^[a-z][A-Za-z0-9]*$")
REQUIRED_FRONTEND_COMPONENTS = {
    "frontend/src/App.tsx",
    "frontend/src/components/DashboardChat.tsx",
    "frontend/src/components/DocumentLibrary.tsx",
    "frontend/src/components/UploadDocuments.tsx",
    "frontend/src/components/DocumentDetail.tsx",
    "frontend/src/components/Evaluation.tsx",
}
REQUIRED_MOCK_REPLACEMENTS = {
    "INITIAL_DOCUMENTS",
    "localAddDeleteState",
    "MOCK_CHUNKS",
    "simulatedPagePreview",
    "PRESET_QASAnswers",
    "PRESET_QASEvidence",
    "presetQuestionButtons",
    "timedFakeIngestion",
    "fakeUploadedMetadata",
    "INITIAL_METRICS",
    "DOMAIN_PERFORMANCE",
    "FAILURE_ANALYSIS_DATA",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def policy_outcome(
    *,
    top_score: float | None,
    threshold: float,
    provider_ready: bool,
    provider_failure: str | None = None,
) -> tuple[int, str, str | None, bool]:
    """Return HTTP status, outcome, error code, and whether provider is called."""
    if top_score is None or top_score < threshold:
        return 200, "insufficient_context", None, False
    if not provider_ready:
        return 503, "provider_unavailable", "GENERATION_PROVIDER_UNAVAILABLE", False
    if provider_failure == "timeout":
        return 504, "provider_error", "GENERATION_TIMEOUT", True
    if provider_failure == "invalid_response":
        return 502, "provider_error", "GENERATION_RESPONSE_INVALID", True
    if provider_failure == "transport":
        return 503, "provider_error", "GENERATION_PROVIDER_ERROR", True
    return 200, "generate", None, True


def _validate_field_names(schemas: dict[str, list[str]]) -> None:
    for schema_name, fields in schemas.items():
        if not fields or len(fields) != len(set(fields)):
            raise ValueError(f"{schema_name} has empty or duplicate field definitions")
        for field in fields:
            for segment in field.split("."):
                if not CAMEL_CASE.fullmatch(segment):
                    raise ValueError(
                        f"{schema_name}.{field} is not a camelCase JSON field path"
                    )


def validate_api_contract(contract: dict[str, Any], root: Path = ROOT) -> None:
    operations = contract["operations"]
    schemas = contract["schemas"]
    error_codes = contract["errorCodes"]
    _validate_field_names(schemas)

    routes: set[tuple[str, str]] = set()
    for operation_name, operation in operations.items():
        route = (operation["method"], operation["path"])
        if route in routes:
            raise ValueError(f"Duplicate method/path pair: {route}")
        routes.add(route)
        if operation["responseSchema"] not in schemas:
            raise ValueError(f"Unknown response schema for {operation_name}")
        request_schema = operation.get("requestSchema")
        if request_schema is not None and request_schema not in schemas:
            raise ValueError(f"Unknown request schema for {operation_name}")
        unknown_errors = set(operation["errors"]) - set(error_codes)
        if unknown_errors:
            raise ValueError(f"Unknown errors for {operation_name}: {unknown_errors}")

    if set(contract["frontendCoverage"]) != REQUIRED_FRONTEND_COMPONENTS:
        raise ValueError("Frontend coverage does not exactly match the reviewed components")
    for relative_path, operation_names in contract["frontendCoverage"].items():
        if not (root / relative_path).is_file():
            raise ValueError(f"Reviewed frontend component is missing: {relative_path}")
        unknown = set(operation_names) - set(operations)
        if unknown:
            raise ValueError(f"Unknown frontend operations for {relative_path}: {unknown}")

    if set(contract["mockReplacementCoverage"]) != REQUIRED_MOCK_REPLACEMENTS:
        raise ValueError("Mock replacement coverage is incomplete or contains stale names")
    for mock_name, operation_names in contract["mockReplacementCoverage"].items():
        unknown = set(operation_names) - set(operations)
        if unknown:
            raise ValueError(f"Unknown operations for mock {mock_name}: {unknown}")

    pagination_fields = set(contract["pagination"]["requiredFields"])
    if pagination_fields != {"items", "page", "pageSize", "total", "totalPages"}:
        raise ValueError("Pagination envelope is not the accepted v1 shape")


def validate_generation_policy(policy: dict[str, Any]) -> None:
    if policy["temperature"] != 0:
        raise ValueError("Generation temperature must be zero")
    if policy["timeoutSeconds"] <= 0:
        raise ValueError("Generation timeout must be positive")
    if policy["maximumConcurrentRequests"] < 1:
        raise ValueError("Generation concurrency bound must be positive")
    readiness = policy["readiness"]
    expected_readiness = {
        "generationIsOptional": True,
        "retrievalReadyWhenGenerationDisabled": True,
        "generationReadyWhenDisabled": False,
        "startupNetworkProbe": False,
    }
    if readiness != expected_readiness:
        raise ValueError("Retrieval-only readiness policy changed")

    threshold = policy["minimumContextScore"]
    scenario_names: set[str] = set()
    for scenario in policy["scenarios"]:
        scenario_names.add(scenario["name"])
        actual = policy_outcome(
            top_score=scenario["topScore"],
            threshold=threshold,
            provider_ready=scenario["providerReady"],
            provider_failure=scenario.get("providerFailure"),
        )
        expected = (
            scenario["expectedHttpStatus"],
            scenario["expectedOutcome"],
            scenario["expectedErrorCode"],
            scenario["providerCalled"],
        )
        if actual != expected:
            raise ValueError(f"Generation scenario failed: {scenario['name']}")
    if len(scenario_names) != len(policy["scenarios"]):
        raise ValueError("Generation scenarios must have unique names")


def validate_cross_contract_alignment(
    api_contract: dict[str, Any],
    generation_policy: dict[str, Any],
    embedding_config: dict[str, Any],
    threshold_summary: dict[str, Any],
) -> None:
    threshold = threshold_summary["selection"]["threshold"]
    configured_thresholds = {
        api_contract["retrieval"]["minimumContextScore"],
        generation_policy["minimumContextScore"],
        threshold,
    }
    if configured_thresholds != {0.46}:
        raise ValueError(f"Threshold contracts disagree: {configured_thresholds}")

    embedding = embedding_config["embedding"]
    chunking = embedding_config["chunking"]
    if embedding["effective_max_tokens"] != 256 or embedding["dimension"] != 384:
        raise ValueError("Selected embedding contract changed")
    if (
        chunking["target_content_tokens"],
        chunking["maximum_content_tokens"],
        chunking["overlap_content_tokens"],
    ) != (220, 240, 60):
        raise ValueError("Selected chunking contract changed")
    if embedding_config["benchmark"]["chunks_above_effective_model_limit"] != 0:
        raise ValueError("Selected embedding benchmark contains truncated chunks")

    api_errors = api_contract["errorCodes"]
    for scenario in generation_policy["scenarios"]:
        error_code = scenario["expectedErrorCode"]
        if error_code and api_errors[error_code] != scenario["expectedHttpStatus"]:
            raise ValueError(f"HTTP status mismatch for {error_code}")


def verify(root: Path = ROOT) -> dict[str, int | float | str]:
    api_contract = load_json(root / API_CONTRACT_PATH.relative_to(ROOT))
    generation_policy = load_json(root / GENERATION_POLICY_PATH.relative_to(ROOT))
    embedding_config = load_json(root / EMBEDDING_CONFIG_PATH.relative_to(ROOT))
    threshold_summary = load_json(root / THRESHOLD_SUMMARY_PATH.relative_to(ROOT))
    validate_api_contract(api_contract, root)
    validate_generation_policy(generation_policy)
    validate_cross_contract_alignment(
        api_contract,
        generation_policy,
        embedding_config,
        threshold_summary,
    )
    return {
        "contractVersion": api_contract["contractVersion"],
        "operations": len(api_contract["operations"]),
        "schemas": len(api_contract["schemas"]),
        "frontendComponents": len(api_contract["frontendCoverage"]),
        "mockReplacements": len(api_contract["mockReplacementCoverage"]),
        "generationScenarios": len(generation_policy["scenarios"]),
        "minimumContextScore": generation_policy["minimumContextScore"],
    }


def main() -> int:
    print(json.dumps(verify(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
