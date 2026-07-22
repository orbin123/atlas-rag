from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import Query
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.main import create_app


def test_liveness_preserves_safe_request_id(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "requestId": "test-request-123"}
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_lifespan_migration_preserves_json_logging(client: TestClient) -> None:
    client.get("/health/live")

    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "bad id value"})

    generated = response.json()["requestId"]
    assert uuid.UUID(generated).version == 4
    assert response.headers["X-Request-ID"] == generated


def test_readiness_is_truthful_before_verified_index(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["retrievalReady"] is False
    assert payload["generationReady"] is False
    assert payload["checks"]["database"]["ready"] is True
    assert payload["checks"]["index"]["ready"] is False
    assert payload["checks"]["embedding"]["ready"] is False
    assert payload["checks"]["worker"]["ready"] is False
    assert payload["checks"]["generation"]["ready"] is False


def test_system_info_reports_empty_database_and_accepted_policy(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["corpus"] == {"documentCount": 0, "pageCount": 0, "chunkCount": 0}
    assert payload["index"] == {
        "status": "not_ready",
        "type": "IndexIDMap2/IndexFlatIP",
        "version": None,
        "vectorCount": 0,
        "dimension": 384,
    }
    assert payload["embedding"]["maxInputTokens"] == 256
    assert payload["chunking"] == {
        "version": "atlas-page-sentence-v1",
        "targetTokens": 220,
        "maxTokens": 240,
        "overlapTokens": 60,
    }
    assert payload["retrieval"]["minimumContextScore"] == 0.46
    assert payload["retrieval"]["rerankerEnabled"] is False
    assert payload["generation"]["enabled"] is False
    assert payload["capabilities"] == {
        "ocr": False,
        "supportedFileTypes": ["pdf", "docx", "txt"],
        "maximumUploadBytes": 50 * 1024 * 1024,
    }


def test_validation_errors_use_stable_envelope(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/validation-probe")
    def validation_probe(limit: int = Query(ge=1, le=5)) -> dict[str, int]:
        return {"limit": limit}

    with TestClient(app) as local_client:
        response = local_client.get(
            "/validation-probe?limit=99", headers={"X-Request-ID": "validation-request"}
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "The request is invalid."
    assert payload["error"]["requestId"] == "validation-request"
    assert payload["error"]["details"]["fields"][0]["location"] == ["query", "limit"]


def test_cors_allows_only_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/system/info",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_openapi_implements_phase_one_contract_operations(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    operations = {
        openapi["paths"]["/health/live"]["get"]["operationId"],
        openapi["paths"]["/health/ready"]["get"]["operationId"],
        openapi["paths"]["/api/v1/system/info"]["get"]["operationId"],
    }
    contract_path = Path(__file__).resolve().parents[2] / "contracts" / "api_v1.json"
    contract = json.loads(contract_path.read_text())

    assert operations == {"getLiveness", "getReadiness", "getSystemInfo"}
    assert operations <= set(contract["operations"])
    assert len(openapi["components"]["schemas"]) == len(set(openapi["components"]["schemas"]))
