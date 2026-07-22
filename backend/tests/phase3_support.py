from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.config import Settings


class WordTokenizer:
    def __init__(self) -> None:
        self.words: dict[str, int] = {}
        self.reverse: dict[int, str] = {}

    def encode(
        self, text: str, *, add_special_tokens: bool = False, truncation: bool = False
    ) -> list[int]:
        del truncation
        identifiers: list[int] = []
        for word in text.split():
            if word not in self.words:
                identifier = len(self.words) + 10
                self.words[word] = identifier
                self.reverse[identifier] = word
            identifiers.append(self.words[word])
        return [1, *identifiers, 2] if add_special_tokens else identifiers

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        return " ".join(self.reverse[token] for token in token_ids)

    def __call__(self, text: str, **_: object) -> dict[str, Any]:
        return {"input_ids": self.encode(text, add_special_tokens=True)}


class DeterministicEncoder:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.tokenizer = WordTokenizer()
        self.encode_calls = 0

    def encode(self, texts: Any, *, batch_size: int) -> Any:
        assert batch_size > 0
        self.encode_calls += 1
        vectors = []
        for text in texts:
            digest = hashlib.sha256(str(text).encode()).digest()
            vector = np.asarray(
                [digest[index] + 1 for index in range(self.dimension)], dtype=np.float32
            )
            vector /= np.linalg.norm(vector)
            vectors.append(vector)
        return np.asarray(vectors, dtype=np.float32)


class CountingEncoderFactory:
    def __init__(self, encoder: DeterministicEncoder) -> None:
        self.encoder = encoder
        self.calls = 0

    def __call__(self, settings: Settings) -> DeterministicEncoder:
        assert settings.embedding_dimension == self.encoder.dimension
        self.calls += 1
        return self.encoder


def phase3_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'atlas.db'}",
        storage_root=tmp_path / "storage",
        embedding_dimension=4,
        embedding_max_input_tokens=18,
        embedding_batch_size=2,
        chunk_target_tokens=8,
        chunk_max_tokens=12,
        chunk_overlap_tokens=3,
        worker_poll_interval_seconds=0.05,
        worker_stale_seconds=10,
    )


def write_text_pdf(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)
