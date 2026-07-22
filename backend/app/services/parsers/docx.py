from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.services.parsers.base import ParsedPage, ParserError


def _block_text(block: Any) -> str:
    if hasattr(block, "rows"):
        rows = []
        for row in block.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows.append("\t".join(cells))
        return "\n".join(rows)
    return str(getattr(block, "text", "")).strip()


def parse_docx(path: Path) -> list[ParsedPage]:
    try:
        document = Document(str(path))
        iterator = document.iter_inner_content()
        parts = [text for block in iterator if (text := _block_text(block))]
    except (PackageNotFoundError, OSError, ValueError, KeyError) as exc:
        raise ParserError("The DOCX file could not be read safely.") from exc
    text = "\n\n".join(parts).strip()
    if not text:
        raise ParserError("The DOCX file contains no extractable text.")
    return [ParsedPage(page_number=1, raw_text=text)]
