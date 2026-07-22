from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.lifespan import RuntimeReadiness
from app.db.base import utc_now
from app.db.models import Document, EvaluationRun, IndexState, IngestionJob
from app.services.chunking import PageInput, build_chunks
from app.services.embedding import EmbeddingService
from app.services.evaluation import EvaluationExecutionError, execute_evaluation_run
from app.services.generation import (
    GenerationProviderError,
    GenerationService,
    GenerationTimeoutError,
    GenerationUnavailableError,
)
from app.services.index_coordinator import commit_document_deletion, commit_incremental_document
from app.services.parsers import ParserError, parse_document
from app.services.preprocessing import clean_pages
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class JobProcessingError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


class IngestionWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        embeddings: EmbeddingService,
        retrieval: RetrievalService,
        generation: GenerationService,
        readiness: RuntimeReadiness,
        on_index_committed: Callable[[Any], None],
        get_active_index: Callable[[], Any],
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.embeddings = embeddings
        self.retrieval = retrieval
        self.generation = generation
        self.readiness = readiness
        self.on_index_committed = on_index_committed
        self.get_active_index = get_active_index
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._process_lock = FileLock(settings.storage_root / "worker.lock")

    async def start(self) -> bool:
        try:
            self._process_lock.acquire(timeout=0)
        except Timeout:
            self.readiness.index_diagnostic = "Another durable worker owns the local queue."
            return False
        try:
            await self.embeddings.load()
            self.readiness.embedding_ready = True
            await asyncio.to_thread(self._reconcile_startup)
            self._task = asyncio.create_task(self._run(), name="atlas-ingestion-worker")
            self.readiness.worker_ready = True
            self._wake.set()
            logger.info("Durable ingestion worker started", extra={"event": "worker_started"})
            return True
        except Exception as exc:
            self._process_lock.release()
            self.readiness.embedding_ready = False
            self.readiness.worker_ready = False
            self.readiness.index_diagnostic = (
                f"Embedding/worker startup failed: {type(exc).__name__}"
            )
            logger.exception(
                "Durable worker startup failed",
                extra={"event": "worker_start_failed", "exceptionType": type(exc).__name__},
            )
            return False

    def kick(self) -> None:
        self._wake.set()

    async def stop(self) -> None:
        self.readiness.worker_ready = False
        self._stopping.set()
        self._wake.set()
        if self._task is not None:
            await self._task
            self._task = None
        if self._process_lock.is_locked:
            self._process_lock.release()
        logger.info("Durable ingestion worker stopped", extra={"event": "worker_stopped"})

    def _reconcile_startup(self) -> None:
        # Acquiring the sole process lock proves every inherited running job is stale.
        with self.session_factory.begin() as session:
            running = session.scalars(
                select(IngestionJob).where(
                    IngestionJob.kind.in_(["ingest", "delete", "evaluation"]),
                    IngestionJob.status == "running",
                )
            ).all()
            for job in running:
                document = session.get(Document, job.document_id) if job.document_id else None
                if job.attempt < job.max_attempts:
                    job.status = "queued"
                    job.stage = "validating"
                    job.progress_percent = 0
                    job.stage_message = "Recovered after an interrupted worker; retry queued."
                    job.error_code = "WORKER_INTERRUPTED"
                    job.error_message = "The previous worker stopped before finalization."
                    job.completed_at = None
                    if document is not None:
                        document.status = "deleting" if job.kind == "delete" else "queued"
                    if job.kind == "evaluation":
                        run = session.scalar(
                            select(EvaluationRun).where(EvaluationRun.job_id == job.id)
                        )
                        if run is not None:
                            run.status = "queued"
                            run.error_code = "WORKER_INTERRUPTED"
                            run.error_message = job.error_message
                else:
                    job.status = "failed"
                    job.error_code = "WORKER_INTERRUPTED"
                    job.error_message = "Retry limit reached after an interrupted worker."
                    job.completed_at = utc_now()
                    if document is not None:
                        document.status = "failed"
                        document.failure_code = job.error_code
                        document.failure_message = job.error_message
                    if job.kind == "evaluation":
                        run = session.scalar(
                            select(EvaluationRun).where(EvaluationRun.job_id == job.id)
                        )
                        if run is not None:
                            run.status = "failed"
                            run.error_code = "WORKER_INTERRUPTED"
                            run.error_message = job.error_message
                            run.completed_at = job.completed_at
        temporary = self.settings.storage_root / "temp"
        if temporary.exists():
            for staged in temporary.glob("*.upload"):
                staged.unlink(missing_ok=True)
            with self.session_factory() as session:
                for tombstone in temporary.glob("*.delete"):
                    document_id = tombstone.name.split(".", 1)[0]
                    if session.get(Document, document_id) is None:
                        tombstone.unlink(missing_ok=True)

    def _claim(self) -> str | None:
        with self.session_factory.begin() as session:
            job = session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.kind.in_(["ingest", "delete", "evaluation"]),
                    IngestionJob.status == "queued",
                )
                .order_by(IngestionJob.created_at, IngestionJob.id)
                .limit(1)
            )
            if job is None:
                return None
            now = utc_now()
            job.status = "running"
            job.stage = "evaluating" if job.kind == "evaluation" else "validating"
            job.progress_percent = 1
            job.stage_message = (
                "Preparing the versioned evaluation run."
                if job.kind == "evaluation"
                else "Validating stored upload."
            )
            job.attempt += 1
            job.started_at = job.started_at or now
            job.heartbeat_at = now
            job.error_code = None
            job.error_message = None
            if job.document_id:
                document = session.get(Document, job.document_id)
                if document is not None:
                    document.status = "deleting" if job.kind == "delete" else "processing"
                    document.failure_code = None
                    document.failure_message = None
            if job.kind == "evaluation":
                run = session.scalar(select(EvaluationRun).where(EvaluationRun.job_id == job.id))
                if run is not None:
                    run.status = "running"
                    run.started_at = run.started_at or now
                    run.error_code = None
                    run.error_message = None
            return job.id

    def _progress(self, job_id: str, stage: str, percent: int, message: str) -> None:
        with self.session_factory.begin() as session:
            job = session.get(IngestionJob, job_id)
            if job is None or job.status != "running":
                return
            job.stage = stage
            job.progress_percent = percent
            job.stage_message = message
            job.heartbeat_at = utc_now()

    def _job_document(self, job_id: str) -> tuple[str, str, Path]:
        with self.session_factory() as session:
            job = session.get(IngestionJob, job_id)
            if job is None or not job.document_id:
                raise JobProcessingError(
                    "DOCUMENT_NOT_FOUND",
                    "The ingestion document record is missing.",
                    retryable=False,
                )
            document = session.get(Document, job.document_id)
            if document is None:
                raise JobProcessingError(
                    "DOCUMENT_NOT_FOUND",
                    "The ingestion document record is missing.",
                    retryable=False,
                )
            if document.status == "indexed":
                return document.id, document.file_type, Path()
            root = self.settings.storage_root.resolve()
            path = (root / document.storage_path).resolve()
            if root not in path.parents or not path.is_file() or path.is_symlink():
                raise JobProcessingError(
                    "INVALID_FILE_CONTENT",
                    "The stored upload is missing or unsafe.",
                    retryable=False,
                )
            return document.id, document.file_type, path

    def _finish_existing(self, job_id: str, document_id: str) -> None:
        with self.session_factory.begin() as session:
            job = session.get_one(IngestionJob, job_id)
            document = session.get_one(Document, document_id)
            state = session.get(IndexState, 1)
            job.status = "succeeded"
            job.stage = "finalizing"
            job.progress_percent = 100
            job.stage_message = "Document was already indexed."
            job.result = {
                "documentId": document_id,
                "pageCount": document.page_count,
                "chunkCount": document.chunk_count,
                "indexVersion": state.index_version if state else None,
            }
            job.completed_at = utc_now()

    def _fail(self, job_id: str, failure: JobProcessingError) -> None:
        with self.session_factory.begin() as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            document = session.get(Document, job.document_id) if job.document_id else None
            retry = failure.retryable and job.attempt < job.max_attempts
            job.status = "queued" if retry else "failed"
            job.error_code = failure.code
            job.error_message = failure.safe_message[:1000]
            job.stage_message = (
                f"Attempt {job.attempt} failed; retry queued." if retry else "Ingestion failed."
            )
            job.heartbeat_at = utc_now()
            job.completed_at = None if retry else utc_now()
            if document is not None:
                document.status = (
                    "deleting"
                    if retry and job.kind == "delete"
                    else "queued"
                    if retry
                    else "failed"
                )
                document.failure_code = failure.code
                document.failure_message = failure.safe_message[:1000]
            if job.kind == "evaluation":
                run = session.scalar(select(EvaluationRun).where(EvaluationRun.job_id == job.id))
                if run is not None:
                    run.status = "queued" if retry else "failed"
                    run.error_code = failure.code
                    run.error_message = failure.safe_message[:1000]
                    run.completed_at = None if retry else utc_now()
        if retry:
            self._wake.set()

    async def _process_ingestion(self, job_id: str) -> None:
        try:
            document_id, file_type, path = await asyncio.to_thread(self._job_document, job_id)
            if not path:
                await asyncio.to_thread(self._finish_existing, job_id, document_id)
                return
            await asyncio.to_thread(
                self._progress, job_id, "extracting", 12, f"Extracting {file_type.upper()} text."
            )
            try:
                parsed = await asyncio.to_thread(parse_document, path, file_type)
            except ParserError as exc:
                raise JobProcessingError("INVALID_FILE_CONTENT", str(exc), retryable=False) from exc
            await asyncio.to_thread(
                self._progress, job_id, "cleaning", 30, f"Cleaning {len(parsed)} extracted pages."
            )
            cleaned = await asyncio.to_thread(
                clean_pages, parsed, remove_repeated_margins=file_type == "pdf"
            )
            await asyncio.to_thread(
                self._progress, job_id, "chunking", 48, "Creating tokenizer-safe chunks."
            )
            page_inputs = [
                PageInput(
                    document_id=document_id,
                    page_number=page.page_number,
                    cleaned_text=page.cleaned_text,
                )
                for page in cleaned
            ]
            chunks = await asyncio.to_thread(
                build_chunks, page_inputs, self.embeddings.encoder.tokenizer, self.settings
            )
            if not chunks:
                raise JobProcessingError(
                    "INVALID_FILE_CONTENT",
                    "The document produced no non-empty chunks after cleaning.",
                    retryable=False,
                )
            await asyncio.to_thread(
                self._progress,
                job_id,
                "embedding",
                65,
                f"Embedding {len(chunks)} chunks in bounded batches.",
            )
            try:
                vectors = await self.embeddings.encode(
                    [chunk.cleaned_text for chunk in chunks],
                    batch_size=self.settings.embedding_batch_size,
                )
            except (RuntimeError, ValueError) as exc:
                raise JobProcessingError(
                    "EMBEDDING_FAILED",
                    "The embedding model could not encode this document.",
                    retryable=True,
                ) from exc
            await asyncio.to_thread(
                self._progress,
                job_id,
                "indexing",
                88,
                "Writing and verifying an atomic index snapshot.",
            )
            was_index_ready = self.readiness.index_ready
            was_index_consistent = self.readiness.index_consistent
            self.readiness.index_ready = False
            self.readiness.index_consistent = False
            self.readiness.index_diagnostic = "An atomic index update is being verified."
            try:
                result = await asyncio.to_thread(
                    commit_incremental_document,
                    settings=self.settings,
                    session_factory=self.session_factory,
                    document_id=document_id,
                    job_id=job_id,
                    pages=cleaned,
                    chunks=chunks,
                    vectors=vectors,
                )
            except Exception as exc:
                self.readiness.index_ready = was_index_ready
                self.readiness.index_consistent = was_index_consistent
                self.readiness.index_diagnostic = (
                    "The previous active index remains verified."
                    if was_index_ready and was_index_consistent
                    else "No active index state exists."
                )
                raise JobProcessingError(
                    "INDEX_UPDATE_FAILED",
                    "The document could not be committed to the active index.",
                    retryable=True,
                ) from exc
            self.on_index_committed(result.index)
            self.readiness.index_ready = True
            self.readiness.index_consistent = True
            self.readiness.index_diagnostic = "The active index is verified."
            logger.info(
                "Ingestion job succeeded",
                extra={
                    "event": "ingestion_succeeded",
                    "jobId": job_id,
                    "documentId": document_id,
                    "chunkCount": result.chunk_count,
                    "indexVersion": result.index_version,
                },
            )
        except JobProcessingError as job_failure:
            await asyncio.to_thread(self._fail, job_id, job_failure)
            logger.warning(
                "Ingestion job failed",
                extra={
                    "event": "ingestion_failed",
                    "jobId": job_id,
                    "code": job_failure.code,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            unexpected_failure = JobProcessingError(
                "INGESTION_FAILED", "An unexpected ingestion failure occurred.", retryable=True
            )
            await asyncio.to_thread(self._fail, job_id, unexpected_failure)
            logger.exception(
                "Unexpected ingestion worker failure",
                extra={"event": "ingestion_unexpected", "exceptionType": type(exc).__name__},
            )

    async def _process_deletion(self, job_id: str) -> None:
        try:
            with self.session_factory() as session:
                job = session.get(IngestionJob, job_id)
                if job is None or not job.document_id:
                    raise JobProcessingError(
                        "DOCUMENT_NOT_FOUND",
                        "The deletion document record is missing.",
                        retryable=False,
                    )
                document_id = job.document_id
            await asyncio.to_thread(
                self._progress,
                job_id,
                "indexing",
                40,
                "Removing document vectors from a candidate snapshot.",
            )
            was_index_ready = self.readiness.index_ready
            was_index_consistent = self.readiness.index_consistent
            self.readiness.index_ready = False
            self.readiness.index_consistent = False
            self.readiness.index_diagnostic = "An atomic document deletion is being verified."
            try:
                result = await asyncio.to_thread(
                    commit_document_deletion,
                    settings=self.settings,
                    session_factory=self.session_factory,
                    document_id=document_id,
                    job_id=job_id,
                )
            except Exception as exc:
                self.readiness.index_ready = was_index_ready
                self.readiness.index_consistent = was_index_consistent
                self.readiness.index_diagnostic = (
                    "The previous active index remains verified."
                    if was_index_ready and was_index_consistent
                    else "No active index state exists."
                )
                raise JobProcessingError(
                    "INDEX_UPDATE_FAILED",
                    "The document could not be removed from the active index.",
                    retryable=True,
                ) from exc
            self.on_index_committed(result.index)
            self.readiness.index_ready = True
            self.readiness.index_consistent = True
            self.readiness.index_diagnostic = "The active index is verified."
            logger.info(
                "Deletion job succeeded",
                extra={
                    "event": "deletion_succeeded",
                    "jobId": job_id,
                    "documentId": document_id,
                    "chunkCount": result.removed_chunk_count,
                    "indexVersion": result.index_version,
                },
            )
        except JobProcessingError as job_failure:
            await asyncio.to_thread(self._fail, job_id, job_failure)
            logger.warning(
                "Deletion job failed",
                extra={
                    "event": "deletion_failed",
                    "jobId": job_id,
                    "code": job_failure.code,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            unexpected_failure = JobProcessingError(
                "INDEX_UPDATE_FAILED",
                "An unexpected deletion failure occurred.",
                retryable=True,
            )
            await asyncio.to_thread(self._fail, job_id, unexpected_failure)
            logger.exception(
                "Unexpected deletion worker failure",
                extra={"event": "deletion_unexpected", "exceptionType": type(exc).__name__},
            )

    def _evaluation_progress(self, job_id: str, completed: int, total: int) -> None:
        percent = min(95, 5 + int(completed * 90 / total))
        self._progress(
            job_id,
            "evaluating",
            percent,
            f"Evaluated {completed} of {total} versioned questions.",
        )

    def _finish_evaluation_job(self, job_id: str, run_id: str) -> None:
        with self.session_factory.begin() as session:
            job = session.get_one(IngestionJob, job_id)
            run = session.get_one(EvaluationRun, run_id)
            job.status = "succeeded"
            job.stage = "finalizing"
            job.progress_percent = 100
            job.stage_message = "Evaluation metrics and failures are persisted."
            job.result = {
                "runId": run.id,
                "evaluatedQuestions": run.evaluated_questions,
                "indexVersion": run.index_version,
            }
            job.heartbeat_at = utc_now()
            job.completed_at = utc_now()

    async def _process_evaluation(self, job_id: str) -> None:
        try:
            with self.session_factory.begin() as session:
                job = session.get(IngestionJob, job_id)
                run = session.scalar(select(EvaluationRun).where(EvaluationRun.job_id == job_id))
                state = session.get(IndexState, 1)
                if job is None or run is None:
                    raise JobProcessingError(
                        "EVALUATION_RUN_NOT_FOUND",
                        "The queued evaluation run is missing.",
                        retryable=False,
                    )
                if state is None:
                    raise JobProcessingError(
                        "INDEX_NOT_READY", "No active index is available.", retryable=True
                    )
                if run.evaluated_questions and run.index_version != state.index_version:
                    raise JobProcessingError(
                        "INDEX_UPDATE_FAILED",
                        "The active index changed before an interrupted evaluation could resume.",
                        retryable=False,
                    )
                run.index_version = state.index_version
                configuration = dict(run.configuration)
                configuration["indexVersion"] = state.index_version
                run.configuration = configuration
                run.status = "running"
            index = self.get_active_index()
            if index is None:
                raise JobProcessingError(
                    "INDEX_NOT_READY", "No active in-memory index is available.", retryable=True
                )
            await execute_evaluation_run(
                run_id=run.id,
                settings=self.settings,
                session_factory=self.session_factory,
                retrieval=self.retrieval,
                generation=self.generation,
                index=index,
                progress=lambda completed, total: self._evaluation_progress(
                    job_id, completed, total
                ),
            )
            await asyncio.to_thread(self._finish_evaluation_job, job_id, run.id)
            logger.info(
                "Evaluation job succeeded",
                extra={"event": "evaluation_succeeded", "jobId": job_id, "runId": run.id},
            )
        except EvaluationExecutionError as exc:
            failure = JobProcessingError(exc.code, exc.safe_message, retryable=exc.retryable)
            await asyncio.to_thread(self._fail, job_id, failure)
        except GenerationUnavailableError:
            await asyncio.to_thread(
                self._fail,
                job_id,
                JobProcessingError(
                    "EVALUATION_MODE_UNAVAILABLE",
                    "The generation provider is unavailable.",
                    retryable=False,
                ),
            )
        except GenerationTimeoutError:
            await asyncio.to_thread(
                self._fail,
                job_id,
                JobProcessingError(
                    "GENERATION_TIMEOUT", "The generation provider timed out.", retryable=True
                ),
            )
        except GenerationProviderError:
            await asyncio.to_thread(
                self._fail,
                job_id,
                JobProcessingError(
                    "GENERATION_PROVIDER_ERROR",
                    "The generation provider request failed.",
                    retryable=True,
                ),
            )
        except JobProcessingError as failure:
            await asyncio.to_thread(self._fail, job_id, failure)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            await asyncio.to_thread(
                self._fail,
                job_id,
                JobProcessingError(
                    "EVALUATION_FAILED",
                    "An unexpected evaluation failure occurred.",
                    retryable=True,
                ),
            )
            logger.exception(
                "Unexpected evaluation worker failure",
                extra={"event": "evaluation_unexpected", "exceptionType": type(exc).__name__},
            )

    async def _process(self, job_id: str) -> None:
        with self.session_factory() as session:
            job = session.get(IngestionJob, job_id)
            kind = job.kind if job is not None else None
        if kind == "delete":
            await self._process_deletion(job_id)
        elif kind == "evaluation":
            await self._process_evaluation(job_id)
        else:
            await self._process_ingestion(job_id)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            self._wake.clear()
            job_id = await asyncio.to_thread(self._claim)
            if job_id is not None:
                await self._process(job_id)
                continue
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=self.settings.worker_poll_interval_seconds
                )
            except TimeoutError:
                continue
