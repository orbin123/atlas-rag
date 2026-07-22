from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_exposes_all_phase_six_operations(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    expected = {
        ("/api/v1/evaluation/runs", "post"): "createEvaluationRun",
        ("/api/v1/evaluation/runs", "get"): "listEvaluationRuns",
        ("/api/v1/evaluation/runs/{runId}", "get"): "getEvaluationRun",
        ("/api/v1/evaluation/runs/{runId}/domains", "get"): "listEvaluationDomains",
        ("/api/v1/evaluation/runs/{runId}/failures", "get"): "listEvaluationFailures",
        ("/api/v1/evaluation/latest", "get"): "getLatestEvaluation",
    }
    for (path, method), operation_id in expected.items():
        assert openapi["paths"][path][method]["operationId"] == operation_id

    request = openapi["components"]["schemas"]["EvaluationRunRequest"]
    assert set(request["properties"]) == {"mode", "maximumQuestions"}
    summary = openapi["components"]["schemas"]["EvaluationRunSummary"]
    assert "metrics" in summary["required"]


def test_phase_six_errors_and_empty_collections_are_typed(client: TestClient) -> None:
    listing = client.get("/api/v1/evaluation/runs")
    assert listing.status_code == 200
    assert listing.json() == {
        "items": [],
        "page": 1,
        "pageSize": 25,
        "total": 0,
        "totalPages": 0,
    }

    create = client.post("/api/v1/evaluation/runs", json={})
    assert create.status_code == 503
    assert create.json()["error"]["code"] == "INDEX_NOT_READY"

    latest = client.get("/api/v1/evaluation/latest")
    assert latest.status_code == 503
    assert latest.json()["error"]["code"] == "EVALUATION_DATASET_MISSING"

    missing = client.get("/api/v1/evaluation/runs/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVALUATION_RUN_NOT_FOUND"

    invalid = client.post(
        "/api/v1/evaluation/runs", json={"mode": "retrieval", "maximumQuestions": 0}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
