#!/usr/bin/env python3
"""Download the Atlas 60 source plan into data/ with provenance metadata.

Uses only the Python standard library plus lxml and pypdf from the Codex
workspace runtime.  Run with the bundled interpreter noted in README below.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler

from lxml import html
from pypdf import PdfReader


USER_AGENT = "atlas-rag-source-archiver/1.0 (+local research corpus build)"
TIMEOUT_SECONDS = 60
PDF_PATTERN = re.compile(r"\.pdf(?:[?#]|$)", re.I)
LICENSE_PATTERN = re.compile(
    r"(?:CC\s*0|CC0|Creative Commons|CC BY(?:-[A-Z]+)*\s*[0-9.]*(?:\s+International)?|"
    r"public domain|public-domain|U\.S\. Government|United States Government|copyright)",
    re.I,
)

# Official replacements for URLs that have been retired or whose current landing
# page no longer exposes a working file link. The manifest retains the plan URL
# in `requested_url` and records the replacement in `downloaded_url`.
RESOLVED_URL_OVERRIDES = {
    "finance_04": "https://documents1.worldbank.org/curated/en/513831574784180010/pdf/Global-Financial-Development-Report-2019-2020-Bank-Regulation-and-Supervision-a-Decade-after-the-Global-Financial-Crisis.pdf",
    "climate_02": "https://prod-01-asg-www-climate.woc.noaa.gov/news-features/understanding-climate/climate-change-atmospheric-carbon-dioxide",
    "climate_03": "https://prod-01-asg-www-climate.woc.noaa.gov/news-features/understanding-climate/climate-change-global-sea-level",
}


def fetch(url: str) -> tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.1"})
    opener = build_opener(HTTPRedirectHandler())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read(), response.geturl(), response.headers.get_content_type()
    except HTTPError as error:
        # NOAA currently admits a normal browser User-Agent but rejects urllib's
        # TLS/client fingerprint. Retry once with curl; do not evade challenges.
        if error.code not in {403, 429}:
            raise
    with tempfile.NamedTemporaryFile() as body:
        result = subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", str(TIMEOUT_SECONDS),
             "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
             "--output", body.name, "--write-out", "%{url_effective}\\n%{content_type}", url],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise HTTPError(url, 403, result.stderr.strip() or "access denied", None, None)
        actual_url, content_type = result.stdout.rsplit("\n", 1)
        return Path(body.name).read_bytes(), actual_url, content_type or "application/octet-stream"


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def text_from_html(blob: bytes) -> str:
    document = html.fromstring(blob)
    for node in document.xpath("//script|//style|//noscript|//svg|//header|//footer|//nav|//aside|//form"):
        node.drop_tree()
    candidates = document.xpath("//main|//article|//*[@role='main']")
    root = candidates[0] if candidates else document.body if document.body is not None else document
    chunks = [re.sub(r"\s+", " ", item).strip() for item in root.xpath(".//text()")]
    chunks = [item for item in chunks if item]
    title = document.xpath("string(//title)").strip()
    return (title + "\n\n" if title else "") + "\n\n".join(chunks) + "\n"


def links_from_html(blob: bytes, base_url: str) -> list[str]:
    document = html.fromstring(blob)
    links = []
    for href in document.xpath("//a[@href]/@href"):
        absolute = urljoin(base_url, href)
        if absolute.startswith("https://") or absolute.startswith("http://"):
            links.append(absolute)
    # Some sites expose download URLs only in embedded JSON or script data.
    decoded = blob.decode("utf-8", "ignore").replace("\\/", "/")
    links.extend(re.findall(r"https?://[^\"'<>\\ ]+?\.pdf(?:\?[^\"'<>\\ ]*)?", decoded, re.I))
    return list(dict.fromkeys(links))


def pick_pdf(links: list[str], title: str) -> str | None:
    candidates = [link for link in links if PDF_PATTERN.search(link)]
    if not candidates:
        return None
    words = set(re.findall(r"[a-z0-9]{4,}", title.lower()))
    return max(candidates, key=lambda link: sum(word in link.lower() for word in words))


def pdf_page_count(path: Path) -> int:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def license_check(text: str, expected: str) -> tuple[str, str]:
    match = LICENSE_PATTERN.search(text)
    if match:
        excerpt = re.sub(r"\s+", " ", text[max(0, match.start() - 100):match.end() + 180]).strip()
        return "matched", excerpt[:400]
    return "not found automatically", f"Expected usage note from plan: {expected}"


def download_item(row: dict[str, str], output: Path) -> dict[str, str]:
    item_id, title, requested_type, source_url = (row[key] for key in ("document_id", "target_title_or_topic", "preferred_stored_type", "source_url"))
    domain_dir = output / safe_name(row["domain"])
    domain_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    blob, actual_url, content_type = fetch(RESOLVED_URL_OVERRIDES.get(item_id, source_url))
    is_pdf = requested_type.upper() == "PDF" and (content_type == "application/pdf" or actual_url.lower().split("?")[0].endswith(".pdf"))

    if requested_type.upper() == "PDF" and not is_pdf:
        candidate = pick_pdf(links_from_html(blob, actual_url), title)
        if not candidate:
            raise RuntimeError("No official PDF link found on landing page")
        blob, actual_url, content_type = fetch(candidate)
        is_pdf = content_type == "application/pdf" or blob[:4] == b"%PDF"
        if not is_pdf:
            raise RuntimeError(f"Resolved link was not a PDF: {actual_url}")

    if is_pdf:
        path = domain_dir / f"{item_id}.pdf"
        path.write_bytes(blob)
        pages = str(pdf_page_count(path))
        try:
            reader = PdfReader(str(path))
            license_text = " ".join(page.extract_text() or "" for page in reader.pages[-3:])
        except Exception:
            license_text = ""
        stored_type = "PDF"
    else:
        path = domain_dir / f"{item_id}.txt"
        clean_text = text_from_html(blob)
        path.write_text(clean_text, encoding="utf-8", newline="\n")
        license_text = clean_text
        pages = "n/a (HTML converted to UTF-8 text)"
        stored_type = "TXT"

    check, evidence = license_check(license_text, row["license_or_usage_note"])
    return {
        "document_id": item_id,
        "domain": row["domain"],
        "title": title,
        "stored_type": stored_type,
        "local_path": str(path.relative_to(output.parent)),
        "requested_url": source_url,
        "downloaded_url": actual_url,
        "downloaded_at_utc": fetched_at,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "page_count": pages,
        "licence_plan_note": row["license_or_usage_note"],
        "licence_check": check,
        "licence_evidence": evidence,
        "status": "downloaded",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=Path("docs/atlas60_source_plan.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/atlas60"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    with args.plan.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for index, row in enumerate(rows, 1):
        print(f"[{index}/{len(rows)}] {row['document_id']}", flush=True)
        try:
            manifest.append(download_item(row, args.output))
        except (HTTPError, URLError, RuntimeError, ValueError, OSError) as error:
            manifest.append({
                "document_id": row["document_id"], "domain": row["domain"], "title": row["target_title_or_topic"],
                "stored_type": row["preferred_stored_type"], "local_path": "", "requested_url": row["source_url"],
                "downloaded_url": "", "downloaded_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "sha256": "", "page_count": "", "licence_plan_note": row["license_or_usage_note"],
                "licence_check": "not checked", "licence_evidence": "", "status": f"failed: {error}",
            })
        time.sleep(0.25)
    fields = list(manifest[0])
    with (args.output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    failed = sum(entry["status"] != "downloaded" for entry in manifest)
    print(f"Completed {len(manifest) - failed}/{len(manifest)}; manifest: {args.output / 'manifest.csv'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
