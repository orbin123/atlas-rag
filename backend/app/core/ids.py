from __future__ import annotations

import hashlib
import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def stable_vector_id(chunk_id: str) -> int:
    """Map a valid UUID to a deterministic positive signed 64-bit FAISS ID."""

    chunk_uuid = uuid.UUID(chunk_id)
    digest = hashlib.sha256(chunk_uuid.bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) & ((1 << 63) - 1)
