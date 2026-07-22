from __future__ import annotations

from app.schemas.common import CamelModel, ComponentCheck


class LivenessResponse(CamelModel):
    status: str
    request_id: str


class ReadinessChecks(CamelModel):
    database: ComponentCheck
    index: ComponentCheck
    embedding: ComponentCheck
    worker: ComponentCheck
    generation: ComponentCheck


class ReadinessResponse(CamelModel):
    status: str
    retrieval_ready: bool
    generation_ready: bool
    checks: ReadinessChecks
    request_id: str
