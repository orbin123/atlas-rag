from __future__ import annotations

from app.schemas.common import CamelModel


class CorpusInfo(CamelModel):
    document_count: int
    page_count: int
    chunk_count: int


class IndexInfo(CamelModel):
    status: str
    type: str
    version: str | None
    vector_count: int
    dimension: int


class EmbeddingInfo(CamelModel):
    model: str
    revision: str
    dimension: int
    max_input_tokens: int


class ChunkingInfo(CamelModel):
    version: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int


class RetrievalInfo(CamelModel):
    default_top_k: int
    maximum_top_k: int
    minimum_context_score: float
    duplicate_similarity_threshold: float
    reranker_enabled: bool


class GenerationInfo(CamelModel):
    enabled: bool
    ready: bool
    provider: str
    model: str | None
    timeout_seconds: int
    maximum_concurrent_requests: int


class CapabilityInfo(CamelModel):
    ocr: bool
    supported_file_types: list[str]
    maximum_upload_bytes: int


class SystemInfoResponse(CamelModel):
    corpus: CorpusInfo
    index: IndexInfo
    embedding: EmbeddingInfo
    chunking: ChunkingInfo
    retrieval: RetrievalInfo
    generation: GenerationInfo
    capabilities: CapabilityInfo
