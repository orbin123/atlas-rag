from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.core.config import Settings
from app.services.chunking import PageInput, build_chunks
from app.services.embedding import validated_embeddings


class WordTokenizer:
    def __init__(self) -> None:
        self.words: dict[str, int] = {}
        self.reverse: dict[int, str] = {}

    def encode(
        self, text: str, *, add_special_tokens: bool = False, truncation: bool = False
    ) -> list[int]:
        del truncation
        ids: list[int] = []
        for word in text.split():
            if word not in self.words:
                identifier = len(self.words) + 10
                self.words[word] = identifier
                self.reverse[identifier] = word
            ids.append(self.words[word])
        return [1, *ids, 2] if add_special_tokens else ids

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        return " ".join(self.reverse[token] for token in token_ids)

    def __call__(self, text: str, **_: object) -> dict[str, Any]:
        return {"input_ids": self.encode(text, add_special_tokens=True)}


def chunk_settings(tmp_path: Any) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_root=tmp_path / "storage",
        embedding_dimension=4,
        embedding_max_input_tokens=8,
        chunk_target_tokens=4,
        chunk_max_tokens=6,
        chunk_overlap_tokens=2,
    )


def test_chunking_enforces_model_limit_overlap_and_stable_ids(tmp_path: Any) -> None:
    settings = chunk_settings(tmp_path)
    tokenizer = WordTokenizer()
    document_id = "561dd01e-4bc9-498a-9e8d-3d6f2e9b6f51"
    pages = [
        PageInput(
            document_id=document_id,
            page_number=1,
            cleaned_text=(
                "one two three four. five six seven eight. "
                "nine ten eleven twelve thirteen fourteen fifteen."
            ),
        ),
        PageInput(document_id=document_id, page_number=2, cleaned_text="  "),
    ]

    first = build_chunks(pages, tokenizer, settings)
    second = build_chunks(pages, tokenizer, settings)

    assert len(first) > 2
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.vector_id for chunk in first] == [chunk.vector_id for chunk in second]
    assert all(chunk.token_count <= settings.chunk_max_tokens for chunk in first)
    assert all(
        chunk.model_input_token_count <= settings.embedding_max_input_tokens for chunk in first
    )
    assert any(chunk.overlap_from_previous_tokens for chunk in first[1:])
    assert [chunk.chunk_index for chunk in first] == list(range(1, len(first) + 1))


class FakeEncoder:
    tokenizer = WordTokenizer()

    def __init__(self, vectors: Any) -> None:
        self.vectors = vectors

    def encode(self, texts: Any, *, batch_size: int) -> Any:
        assert batch_size > 0
        assert len(texts) == len(self.vectors)
        return self.vectors


def test_embedding_validation_accepts_normalized_float32(tmp_path: Any) -> None:
    settings = chunk_settings(tmp_path)
    vectors = [[1, 0, 0, 0], [0, 1, 0, 0]]

    result = validated_embeddings(FakeEncoder(vectors), ["one", "two"], settings)

    assert result.dtype == np.float32
    assert result.flags.c_contiguous


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([[1, 0]], "shape"),
        ([[2, 0, 0, 0]], "normalized"),
        ([[float("nan"), 0, 0, 0]], "non-finite"),
    ],
)
def test_embedding_validation_rejects_invalid_vectors(
    tmp_path: Any, vectors: list[list[float]], message: str
) -> None:
    settings = chunk_settings(tmp_path)

    with pytest.raises(ValueError, match=message):
        validated_embeddings(FakeEncoder(vectors), ["one"], settings)
