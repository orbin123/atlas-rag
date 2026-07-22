from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.parsers.base import ParsedPage, ParserError


def parse_pdf(path: Path) -> list[ParsedPage]:
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ParserError("Encrypted PDF files are not supported.")
        if not reader.pages:
            raise ParserError("The PDF has no pages.")
        pages = [
            ParsedPage(page_number=number, raw_text=page.extract_text() or "")
            for number, page in enumerate(reader.pages, start=1)
        ]
    except ParserError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError, KeyError) as exc:
        raise ParserError("The PDF could not be read safely.") from exc
    if not any(page.raw_text.strip() for page in pages):
        raise ParserError(
            "The PDF contains no extractable text; scanned PDFs require OCR, "
            "which is not supported."
        )
    return pages
