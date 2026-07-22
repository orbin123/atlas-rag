from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from filelock import FileLock
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.ids import new_uuid
from app.db.models import Document, IngestionJob
from app.storage.files import MIME_TYPES, StagedUpload, UploadFileError

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class UploadMetadata:
    domain: str = "user-uploaded"
    title: str | None = None
    author: str | None = None
    source_url: str | None = None
    license_note: str | None = None
    evaluation_questions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcceptedUpload:
    job_id: str
    document_id: str


def _clean_optional(value: str | None, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > maximum or _CONTROL.search(cleaned):
        raise UploadFileError("VALIDATION_ERROR", f"The {field} value is invalid.", 422)
    return cleaned


def validate_metadata(metadata: UploadMetadata) -> UploadMetadata:
    domain = _clean_optional(metadata.domain, field="domain", maximum=255) or "user-uploaded"
    title = _clean_optional(metadata.title, field="title", maximum=512)
    author = _clean_optional(metadata.author, field="author", maximum=512)
    license_note = _clean_optional(metadata.license_note, field="license note", maximum=4000)
    source_url = _clean_optional(metadata.source_url, field="source URL", maximum=2048)
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise UploadFileError(
                "VALIDATION_ERROR", "The source URL must be an absolute HTTP(S) URL.", 422
            )
    questions = tuple(
        _clean_optional(question, field="evaluation question", maximum=2000)
        for question in metadata.evaluation_questions
    )
    if any(question is None for question in questions):
        raise UploadFileError("VALIDATION_ERROR", "Evaluation questions cannot be blank.", 422)
    cleaned_questions = tuple(question for question in questions if question is not None)
    if cleaned_questions and len(cleaned_questions) < 3:
        raise UploadFileError(
            "VALIDATION_ERROR",
            "Provide at least three evaluation questions or leave the section empty.",
            422,
        )
    if len(cleaned_questions) != len({question.casefold() for question in cleaned_questions}):
        raise UploadFileError("VALIDATION_ERROR", "Evaluation questions must be unique.", 422)
    return UploadMetadata(
        domain=domain,
        title=title,
        author=author,
        source_url=source_url,
        license_note=license_note,
        evaluation_questions=cleaned_questions,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def accept_staged_upload(
    staged: StagedUpload,
    metadata: UploadMetadata,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> AcceptedUpload:
    document_id = new_uuid()
    job_id = new_uuid()
    safe_name = f"{document_id}.{staged.file_type}"
    originals = settings.storage_root / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    destination = originals / safe_name
    lock = FileLock(settings.storage_root / "upload-accept.lock")
    committed = False
    try:
        validated = validate_metadata(metadata)
        with lock:
            with session_factory() as session:
                duplicate = session.scalar(
                    select(Document).where(Document.sha256 == staged.sha256).limit(1)
                )
                if duplicate is not None:
                    raise UploadFileError(
                        "DUPLICATE_DOCUMENT",
                        "This file is already present in the knowledge base.",
                        409,
                        {"documentId": duplicate.id},
                    )
            os.replace(staged.path, destination)
            _fsync_directory(originals)
            try:
                with session_factory.begin() as session:
                    session.add(
                        Document(
                            id=document_id,
                            original_file_name=staged.original_name,
                            safe_storage_name=safe_name,
                            file_type=staged.file_type,
                            mime_type=MIME_TYPES[staged.file_type],
                            domain=validated.domain,
                            title=validated.title,
                            author=validated.author,
                            source_url=validated.source_url,
                            license_note=validated.license_note,
                            source_kind="upload",
                            relative_source_path=None,
                            storage_path=str(Path("originals") / safe_name),
                            size_bytes=staged.size_bytes,
                            sha256=staged.sha256,
                            page_count=0,
                            chunk_count=0,
                            status="queued",
                        )
                    )
                    if validated.evaluation_questions:
                        # Keep these with the document so a failed upload cannot
                        # contribute cases: evaluation only loads indexed documents.
                        from app.db.models import UploadedEvaluationCase

                        session.add_all(
                            UploadedEvaluationCase(document_id=document_id, question=question)
                            for question in validated.evaluation_questions
                        )
                    session.add(
                        IngestionJob(
                            id=job_id,
                            document_id=document_id,
                            kind="ingest",
                            status="queued",
                            stage="validating",
                            progress_percent=0,
                            stage_message="Upload accepted and queued for validation.",
                            attempt=0,
                            max_attempts=3,
                        )
                    )
                committed = True
            except Exception:
                destination.unlink(missing_ok=True)
                raise
    finally:
        staged.path.unlink(missing_ok=True)
        if not committed:
            destination.unlink(missing_ok=True)
    return AcceptedUpload(job_id=job_id, document_id=document_id)
