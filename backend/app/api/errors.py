from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorBody, ErrorEnvelope

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class APIError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, Any] | list[Any] | None = None


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | list[Any] | None = None,
) -> JSONResponse:
    payload = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details,
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(by_alias=True))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            {
                "location": [str(part) for part in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()[:25]
        ]
        return error_response(
            request,
            code="VALIDATION_ERROR",
            message="The request is invalid.",
            status_code=422,
            details={"fields": field_errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            request,
            code="VALIDATION_ERROR",
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled application error",
            extra={"event": "unhandled_error", "exceptionType": type(exc).__name__},
        )
        return error_response(
            request,
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            status_code=500,
        )
