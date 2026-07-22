from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import CamelModel


class ChatQueryRequest(CamelModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1)
    domain: str | None = Field(default=None, max_length=255)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must contain non-whitespace characters")
        return normalized

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatCitation(CamelModel):
    label: str
    document_id: str
    document_name: str
    page_number: int
    chunk_index: int


class ChatSource(CamelModel):
    label: str
    chunk_id: str
    document_id: str
    document_name: str
    domain: str
    page_number: int
    chunk_index: int
    text: str
    token_count: int
    similarity_score: float
    rank: int


class ChatTiming(CamelModel):
    retrieval_ms: float
    generation_ms: float
    total_ms: float


class ChatConfig(CamelModel):
    top_k: int
    minimum_context_score: float
    index_version: str


class ChatQueryResponse(CamelModel):
    query_id: str
    question: str
    answer: str
    insufficient_context: bool
    insufficient_reason: str | None
    citations: list[ChatCitation]
    sources: list[ChatSource]
    timing: ChatTiming
    config: ChatConfig


class RetrievalConfig(CamelModel):
    top_k: int
    domain: str | None
    minimum_context_score: float
    index_version: str | None


class RetrievalTiming(CamelModel):
    retrieval_ms: float


class RetrievalDetailResponse(CamelModel):
    query_id: str
    question: str
    status: str
    insufficient_context: bool
    sources: list[ChatSource]
    timing: RetrievalTiming
    config: RetrievalConfig
    created_at: datetime


class Suggestion(CamelModel):
    id: str
    question: str
    domain: str
