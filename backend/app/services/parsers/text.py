from __future__ import annotations

from pathlib import Path

from app.services.parsers.base import ParsedPage, ParserError


def decode_text_bytes(content: bytes) -> str:
    if b"\x00" in content:
        raise ParserError("The TXT file contains binary null bytes.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return content.decode("cp1252")
        except UnicodeDecodeError as exc:  # pragma: no cover - cp1252 maps every byte
            raise ParserError("The TXT encoding is not supported.") from exc


def parse_text(path: Path) -> list[ParsedPage]:
    try:
        text = decode_text_bytes(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
    except OSError as exc:
        raise ParserError("The TXT file could not be read.") from exc
    if not text.strip():
        raise ParserError("The TXT file contains no extractable text.")
    return [ParsedPage(page_number=1, raw_text=text)]
