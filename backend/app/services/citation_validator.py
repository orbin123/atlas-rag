from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_CITATION = re.compile(r"\[(S[1-9][0-9]*)\]")


@dataclass(frozen=True, slots=True)
class CitationValidation:
    valid: bool
    labels: tuple[str, ...]
    invalid_labels: tuple[str, ...]


def validate_citations(answer: str, allowed_labels: Sequence[str]) -> CitationValidation:
    allowed = set(allowed_labels)
    observed = tuple(dict.fromkeys(_CITATION.findall(answer)))
    invalid = tuple(label for label in observed if label not in allowed)
    valid = bool(observed) and not invalid
    return CitationValidation(valid=valid, labels=observed, invalid_labels=invalid)
