from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_openapi_exposes_phase_five_operations_and_camel_case_contract(
    client: TestClient,
) -> None:
    openapi = client.get("/openapi.json").json()
    expected = {
        ("/api/v1/chat/queries", "post"): "createChatQuery",
        ("/api/v1/chat/suggestions", "get"): "listChatSuggestions",
        ("/api/v1/retrieval/{queryId}", "get"): "getRetrievalDetail",
    }
    for (path, method), operation_id in expected.items():
        assert openapi["paths"][path][method]["operationId"] == operation_id

    request_schema = openapi["components"]["schemas"]["ChatQueryRequest"]
    assert set(request_schema["properties"]) == {"question", "topK", "domain"}
    assert request_schema["properties"]["question"]["maxLength"] == 2000
    response_schema = openapi["components"]["schemas"]["ChatQueryResponse"]
    assert set(response_schema["required"]) == {
        "queryId",
        "question",
        "answer",
        "insufficientContext",
        "insufficientReason",
        "citations",
        "sources",
        "timing",
        "config",
    }
    contract_path = Path(__file__).resolve().parents[2] / "contracts" / "api_v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert set(expected.values()) <= set(contract["operations"])


def test_phase_five_failures_use_stable_typed_envelopes(client: TestClient) -> None:
    no_index = client.post("/api/v1/chat/queries", json={"question": "Can this be answered?"})
    assert no_index.status_code == 503
    assert no_index.json()["error"]["code"] == "INDEX_NOT_READY"

    missing_dataset = client.get("/api/v1/chat/suggestions")
    assert missing_dataset.status_code == 503
    assert missing_dataset.json()["error"]["code"] == "EVALUATION_DATASET_MISSING"

    invalid_question = client.post("/api/v1/chat/queries", json={"question": "   "})
    assert invalid_question.status_code == 422
    assert invalid_question.json()["error"]["code"] == "VALIDATION_ERROR"

    invalid_limit = client.get("/api/v1/chat/suggestions?limit=21")
    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["error"]["code"] == "VALIDATION_ERROR"
