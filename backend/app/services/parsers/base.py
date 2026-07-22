from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ParserError(ValueError):
    """A safe, user-facing document parsing failure."""


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    raw_text: str


def parse_document(path: Path, file_type: str) -> list[ParsedPage]:
    if file_type == "pdf":
        from app.services.parsers.pdf import parse_pdf

        return parse_pdf(path)
    if file_type == "docx":
        from app.services.parsers.docx import parse_docx

        return parse_docx(path)
    if file_type == "txt":
        from app.services.parsers.text import parse_text

        return parse_text(path)
    raise ParserError("The document type is not supported.")
