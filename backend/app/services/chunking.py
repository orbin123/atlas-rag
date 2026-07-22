from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings
from app.core.ids import stable_vector_id


class Tokenizer(Protocol):
    def encode(
        self, text: str, *, add_special_tokens: bool = False, truncation: bool = False
    ) -> list[int]: ...

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> str: ...

    def __call__(self, text: str, **kwargs: object) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class PageInput:
    document_id: str
    page_number: int
    cleaned_text: str


@dataclass(frozen=True, slots=True)
class BuiltChunk:
    id: str
    document_id: str
    vector_id: int
    chunk_index: int
    page_number: int
    original_text: str
    cleaned_text: str
    token_count: int
    model_input_token_count: int
    overlap_from_previous_tokens: int
    content_sha256: str


def _content_tokens(tokenizer: Tokenizer, text: str) -> list[int]:
    return list(tokenizer.encode(text, add_special_tokens=False, truncation=False))


def _joined_count(tokenizer: Tokenizer, units: Sequence[str]) -> int:
    return len(_content_tokens(tokenizer, "\n\n".join(units)))


def _split_units(text: str, tokenizer: Tokenizer, maximum: int) -> list[str]:
    units: list[str] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    for paragraph in paragraphs:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if sentence.strip()
        ] or [paragraph]
        for sentence in sentences:
            remaining = _content_tokens(tokenizer, sentence)
            if len(remaining) <= maximum:
                units.append(sentence)
                continue
            while remaining:
                low, high = 1, min(maximum, len(remaining))
                accepted_size, accepted_text = 0, ""
                while low <= high:
                    middle = (low + high) // 2
                    decoded = tokenizer.decode(remaining[:middle], skip_special_tokens=True).strip()
                    if decoded and len(_content_tokens(tokenizer, decoded)) <= maximum:
                        accepted_size, accepted_text = middle, decoded
                        low = middle + 1
                    else:
                        high = middle - 1
                if not accepted_size:
                    raise ValueError("Tokenizer could not produce a non-empty safe unit.")
                units.append(accepted_text)
                remaining = remaining[accepted_size:]
    return units


def _overlap(
    tokenizer: Tokenizer, units: Sequence[str], overlap_tokens: int
) -> tuple[list[str], int]:
    if overlap_tokens == 0:
        return [], 0
    selected: list[str] = []
    for unit in reversed(units):
        candidate = [unit, *selected]
        if _joined_count(tokenizer, candidate) <= overlap_tokens:
            selected = candidate
            continue
        if not selected:
            ids = _content_tokens(tokenizer, unit)
            tail = tokenizer.decode(ids[-overlap_tokens:], skip_special_tokens=True).strip()
            if tail:
                selected = [tail]
        break
    return selected, _joined_count(tokenizer, selected) if selected else 0


def build_chunks(
    pages: Sequence[PageInput], tokenizer: Tokenizer, settings: Settings
) -> list[BuiltChunk]:
    chunks: list[BuiltChunk] = []
    indexes: dict[str, int] = {}
    vector_ids: set[int] = set()

    for page in pages:
        text = page.cleaned_text.strip()
        if not text:
            continue
        units = _split_units(text, tokenizer, settings.chunk_max_tokens)
        pending: list[str] = []
        pending_overlap = 0
        page_chunks: list[tuple[list[str], int]] = []

        for unit in units:
            current_count = _joined_count(tokenizer, pending) if pending else 0
            candidate_count = _joined_count(tokenizer, [*pending, unit])
            if pending and (
                current_count >= settings.chunk_target_tokens
                or candidate_count > settings.chunk_max_tokens
            ):
                previous = pending
                page_chunks.append((pending, pending_overlap))
                pending, pending_overlap = _overlap(
                    tokenizer, previous, settings.chunk_overlap_tokens
                )
                while (
                    pending
                    and _joined_count(tokenizer, [*pending, unit]) > settings.chunk_max_tokens
                ):
                    pending = pending[1:]
                    pending_overlap = _joined_count(tokenizer, pending) if pending else 0
            pending.append(unit)
        if pending:
            page_chunks.append((pending, pending_overlap))

        for chunk_units, overlap_count in page_chunks:
            chunk_text = "\n\n".join(chunk_units).strip()
            if not chunk_text:
                continue
            token_count = len(_content_tokens(tokenizer, chunk_text))
            model_tokens = len(
                tokenizer(
                    chunk_text,
                    add_special_tokens=True,
                    truncation=False,
                    return_attention_mask=False,
                )["input_ids"]
            )
            if token_count > settings.chunk_max_tokens:
                raise ValueError("Chunk exceeds the configured content-token maximum.")
            if model_tokens > settings.embedding_max_input_tokens:
                raise ValueError("Chunk would be truncated by the embedding model.")
            chunk_index = indexes.get(page.document_id, 0) + 1
            indexes[page.document_id] = chunk_index
            content_sha = hashlib.sha256(chunk_text.encode()).hexdigest()
            chunk_id = str(
                uuid.uuid5(
                    uuid.UUID(page.document_id),
                    f"page:{page.page_number}:chunk:{chunk_index}:{content_sha}",
                )
            )
            vector_id = stable_vector_id(chunk_id)
            if vector_id in vector_ids:
                raise ValueError(f"Stable vector ID collision for chunk {chunk_id}.")
            vector_ids.add(vector_id)
            chunks.append(
                BuiltChunk(
                    id=chunk_id,
                    document_id=page.document_id,
                    vector_id=vector_id,
                    chunk_index=chunk_index,
                    page_number=page.page_number,
                    original_text=chunk_text,
                    cleaned_text=chunk_text,
                    token_count=token_count,
                    model_input_token_count=model_tokens,
                    overlap_from_previous_tokens=overlap_count,
                    content_sha256=content_sha,
                )
            )
    return chunks
