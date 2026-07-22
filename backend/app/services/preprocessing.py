from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.services.parsers import ParsedPage

_SPACE = re.compile(r"[ \t\f\v]+")
_BLANKS = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ENDS_SENTENCE = re.compile(r"[.!?:;\]\)\"']$")


@dataclass(frozen=True, slots=True)
class CleanedPage:
    page_number: int
    raw_text: str
    cleaned_text: str
    repeated_lines_removed: tuple[str, ...]


def _normalized_line(line: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", line)).strip()


def _margin_lines(pages: Iterable[ParsedPage]) -> set[str]:
    candidates: Counter[str] = Counter()
    non_empty_pages = 0
    for page in pages:
        lines = [_normalized_line(line) for line in page.raw_text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        non_empty_pages += 1
        candidates.update({*lines[:2], *lines[-2:]})
    threshold = max(2, math.ceil(non_empty_pages * 0.6))
    return {line for line, count in candidates.items() if count >= threshold and len(line) <= 200}


def _join_broken_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    pending = ""
    for line in lines:
        if not line:
            if pending:
                paragraphs.append(pending.strip())
                pending = ""
            continue
        if not pending:
            pending = line
        elif pending.endswith("-") and line[:1].islower():
            pending = pending[:-1] + line
        elif not _ENDS_SENTENCE.search(pending) and line[:1].islower():
            pending += " " + line
        else:
            pending += "\n" + line
    if pending:
        paragraphs.append(pending.strip())
    return "\n\n".join(paragraphs)


def clean_pages(pages: list[ParsedPage], *, remove_repeated_margins: bool) -> list[CleanedPage]:
    repeated = _margin_lines(pages) if remove_repeated_margins else set()
    cleaned: list[CleanedPage] = []
    for page in pages:
        normalized = unicodedata.normalize("NFKC", page.raw_text)
        normalized = _CONTROL.sub("", normalized).replace("\r\n", "\n").replace("\r", "\n")
        lines = [_normalized_line(line) for line in normalized.splitlines()]
        removed = tuple(dict.fromkeys(line for line in lines if line and line in repeated))
        informative = [
            "" if not line else line
            for line in lines
            if not line or (line not in repeated and any(character.isalnum() for character in line))
        ]
        text = _BLANKS.sub("\n\n", _join_broken_lines(informative)).strip()
        cleaned.append(
            CleanedPage(
                page_number=page.page_number,
                raw_text=page.raw_text,
                cleaned_text=text,
                repeated_lines_removed=removed,
            )
        )
    return cleaned
