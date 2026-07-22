from __future__ import annotations

import logging
import re
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import install_error_handlers
from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.ids import new_uuid
from app.core.lifespan import build_lifespan
from app.core.logging import bind_request_id, configure_logging, reset_request_id
from app.services.embedding import EncoderFactory
from app.services.generation import GenerationProviderFactory

logger = logging.getLogger(__name__)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def create_app(
    settings: Settings | None = None,
    *,
    encoder_factory: EncoderFactory | None = None,
    generation_provider_factory: GenerationProviderFactory | None = None,
    start_worker: bool | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    app = FastAPI(
        title="Atlas RAG API",
        version=__version__,
        lifespan=build_lifespan(
            resolved_settings,
            encoder_factory=encoder_factory,
            generation_provider_factory=generation_provider_factory,
            start_worker=(
                resolved_settings.env != "test" if start_worker is None else start_worker
            ),
        ),
    )
    app.state.settings = resolved_settings
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        candidate = request.headers.get("X-Request-ID", "")
        request_id = candidate if _SAFE_REQUEST_ID.fullmatch(candidate) else new_uuid()
        request.state.request_id = request_id
        token = bind_request_id(request_id)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            logger.info(
                "Request completed",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "durationMs": duration_ms,
                },
            )
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(v1_router)
    return app


app = create_app()
