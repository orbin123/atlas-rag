#!/usr/bin/env python3
"""Reconcile the Atlas source manifest with files already present on disk."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader


ROOT = Path("data/atlas60")
PLAN = Path("docs/atlas60_source_plan.csv")
MANIFEST = ROOT / "manifest.csv"
MISMATCHES = {
    "health_03": "file is an unrelated Springer epigenetics article, not CDC About Genomics",
    "education_04": "file is an OpenStax blog article, not Educational Psychology chapter 1",
    "law_04": "file is a 2019 Switzerland-only update, not the planned cryptocurrency report item",
    "law_06": "file is an unrelated 1995 U.S. congressional bill, not the planned legal report",
    "history_05": "file is unrelated course material and has no Smithsonian CC0 provenance",
}
LICENSE_PATTERN = re.compile(r"(?:CC\s*0|CC0|Creative Commons|CC BY(?:-[A-Z]+)*\s*[0-9.]*(?:\s+International)?|public domain|U\.S\. Government|United States Government|copyright)", re.I)


def file_for(document_id: str) -> Path | None:
    matches = list(ROOT.glob(f"**/{document_id}.pdf")) + list(ROOT.glob(f"**/{document_id}.txt"))
    return matches[0] if len(matches) == 1 else None


def file_details(path: Path) -> tuple[str, str, str, str]:
    """Return stored type, page count, licence-check result, and evidence."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        pages = str(len(reader.pages))
        text = " ".join(page.extract_text() or "" for page in reader.pages[-3:])
        stored_type = "PDF"
    else:
        text = path.read_text(encoding="utf-8")
        pages = "n/a (HTML converted to UTF-8 text)"
        stored_type = "TXT"
    match = LICENSE_PATTERN.search(text)
    if not match:
        return stored_type, pages, "not found automatically", "No licence statement detected in the stored file."
    evidence = re.sub(r"\s+", " ", text[max(0, match.start()-100):match.end()+180]).strip()
    return stored_type, pages, "matched", evidence[:400]


def main() -> None:
    existing = {row["document_id"]: row for row in csv.DictReader(MANIFEST.open(encoding="utf-8", newline=""))}
    plan = list(csv.DictReader(PLAN.open(encoding="utf-8", newline="")))
    output = []
    for item in plan:
        document_id = item["document_id"]
        prior = existing.get(document_id, {})
        path = file_for(document_id)
        base = {
            "document_id": document_id,
            "domain": item["domain"],
            "title": item["target_title_or_topic"],
            "requested_stored_type": item["preferred_stored_type"],
            "local_path": str(path.relative_to(ROOT.parent)) if path else "",
            "requested_url": item["source_url"],
            "downloaded_url": prior.get("downloaded_url", "") if prior.get("status") == "downloaded" else "",
            "downloaded_at_utc": prior.get("downloaded_at_utc", "") if prior.get("status") == "downloaded" else "",
            "file_modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z") if path else "",
            "licence_plan_note": item["license_or_usage_note"],
        }
        if not path:
            base.update({"stored_type": "", "sha256": "", "page_count": "", "licence_check": "not checked", "licence_evidence": "", "provenance_status": "missing file", "validation_status": "missing"})
        else:
            stored_type, pages, licence_check, evidence = file_details(path)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            known_download = prior.get("status") == "downloaded" and prior.get("sha256") == checksum
            issues = []
            if stored_type != item["preferred_stored_type"]:
                issues.append(f"stored {stored_type}; plan prefers {item['preferred_stored_type']}")
            if document_id in MISMATCHES:
                issues.append(MISMATCHES[document_id])
            base.update({"stored_type": stored_type, "sha256": checksum, "page_count": pages, "licence_check": licence_check, "licence_evidence": evidence})
            if known_download:
                base.update({"provenance_status": "verified by prior archive run", "validation_status": "downloaded"})
            elif issues:
                base.update({"provenance_status": "user-supplied; actual URL/date unavailable", "validation_status": "needs replacement: " + "; ".join(issues)})
            else:
                base.update({"provenance_status": "user-supplied; actual URL/date unavailable", "validation_status": "downloaded — provenance pending"})
        output.append(base)
    fields = list(output[0])
    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    (ROOT / "manifest.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
