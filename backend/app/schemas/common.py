from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer

_CAMEL_BOUNDARY = re.compile(r"_([a-zA-Z])")


def to_camel(value: str) -> str:
    return _CAMEL_BOUNDARY.sub(lambda match: match.group(1).upper(), value)


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime_fields(self, value: Any) -> Any:
        return _serialize_datetime(value) if isinstance(value, datetime) else value


class ErrorBody(CamelModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any] | None = None
    request_id: str


class ErrorEnvelope(CamelModel):
    error: ErrorBody


class ComponentCheck(CamelModel):
    ready: bool
    detail: str


class PaginationParams(CamelModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


ItemT = TypeVar("ItemT")


class PaginatedResponse(CamelModel, Generic[ItemT]):
    items: list[ItemT]
    page: int
    page_size: int
    total: int
    total_pages: int
