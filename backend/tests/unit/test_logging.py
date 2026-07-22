from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, bind_request_id, reset_request_id


def test_json_formatter_includes_safe_context() -> None:
    formatter = JsonFormatter()
    token = bind_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="atlas.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Ignored human message",
            args=(),
            exc_info=None,
        )
        record.event = "test_event"
        record.jobId = "job-1"
        payload = json.loads(formatter.format(record))
    finally:
        reset_request_id(token)

    assert payload["level"] == "INFO"
    assert payload["event"] == "test_event"
    assert payload["requestId"] == "request-123"
    assert payload["jobId"] == "job-1"
    assert payload["timestamp"].endswith("Z")
