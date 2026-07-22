from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.db.migrations import upgrade_database
from app.db.models import IndexState
from app.db.session import create_database_engine, create_session_factory
from app.services.embedding import EmbeddingService, EncoderFactory, SentenceTransformerEncoder
from app.services.generation import (
    GenerationProviderFactory,
    build_generation_service,
)
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeReadiness:
    database_ready: bool = False
    index_ready: bool = False
    index_consistent: bool = False
    embedding_ready: bool = False
    worker_ready: bool = False
    index_diagnostic: str = "No active index state exists."


def _ensure_storage_layout(storage_root: Path) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    for name in ("originals", "indexes", "temp", "evaluation"):
        (storage_root / name).mkdir(exist_ok=True)


def build_lifespan(
    settings: Settings,
    *,
    encoder_factory: EncoderFactory | None = None,
    generation_provider_factory: GenerationProviderFactory | None = None,
    start_worker: bool = True,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        readiness = RuntimeReadiness()
        app.state.readiness = readiness
        _ensure_storage_layout(settings.storage_root)
        upgrade_database(settings.database_url)
        engine = create_database_engine(settings.database_url)
        session_factory = create_session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        readiness.database_ready = True
        from app.services.snapshots import verify_active_snapshot

        with session_factory() as session:
            report = verify_active_snapshot(session, settings)
        readiness.index_ready = report.ready
        readiness.index_consistent = report.ready
        readiness.index_diagnostic = (
            "The active index is verified." if report.ready else "; ".join(report.errors)
        )
        app.state.active_index = report.index
        logger.info("Database ready", extra={"event": "database_ready"})
        if report.ready:
            logger.info(
                "Active index verified",
                extra={
                    "event": "index_verified",
                    "indexVersion": report.index_version,
                    "vectorCount": report.vector_count,
                },
            )
        else:
            logger.warning(
                "Active index is not ready",
                extra={"event": "index_not_ready", "reason": readiness.index_diagnostic},
            )
        embeddings = EmbeddingService(
            settings,
            encoder_factory=encoder_factory or SentenceTransformerEncoder,
        )
        app.state.embedding_service = embeddings
        app.state.retrieval_service = RetrievalService(settings, embeddings)
        generation = build_generation_service(settings, generation_provider_factory)
        app.state.generation_service = generation
        worker = None
        if start_worker:
            with session_factory() as session:
                has_index_state = session.get(IndexState, 1) is not None
            if not has_index_state or report.ready:
                from app.workers.runner import IngestionWorker

                worker = IngestionWorker(
                    settings=settings,
                    session_factory=session_factory,
                    embeddings=embeddings,
                    retrieval=app.state.retrieval_service,
                    generation=generation,
                    readiness=readiness,
                    on_index_committed=lambda index: setattr(app.state, "active_index", index),
                    get_active_index=lambda: app.state.active_index,
                )
                app.state.ingestion_worker = worker
                await worker.start()
            else:
                readiness.worker_ready = False
                readiness.embedding_ready = False
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            await generation.close()
            readiness.database_ready = False
            engine.dispose()
            logger.info("Application stopped", extra={"event": "application_stopped"})

    return lifespan
