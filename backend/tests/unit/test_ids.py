from __future__ import annotations

import uuid

import pytest

from app.core.ids import new_uuid, stable_vector_id


def test_new_uuid_returns_distinct_valid_uuids() -> None:
    first = new_uuid()
    second = new_uuid()

    assert uuid.UUID(first).version == 4
    assert uuid.UUID(second).version == 4
    assert first != second


def test_vector_id_is_deterministic_signed_64_bit() -> None:
    chunk_id = "aaf2fd3f-cfd0-47d0-8091-f04a6f7cffef"

    vector_id = stable_vector_id(chunk_id)

    assert vector_id == stable_vector_id(chunk_id)
    assert 0 <= vector_id <= (1 << 63) - 1


def test_vector_id_rejects_non_uuid() -> None:
    with pytest.raises(ValueError, match="badly formed"):
        stable_vector_id("not-a-uuid")
