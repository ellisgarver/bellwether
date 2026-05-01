"""Standalone ProQuest TDM Studio dataset export script.

Run this INSIDE the TDM Studio Jupyter environment. It has no external
dependencies beyond the proquest_tdm client that is pre-installed in every
TDM Studio kernel.

Usage (TDM Studio terminal):
    PROQUEST_DATASET_ID=<your-dataset-id> python tdm_studio_export.py

Usage (TDM Studio notebook cell):
    import os
    os.environ["PROQUEST_DATASET_ID"] = "<your-dataset-id>"
    %run tdm_studio_export.py

Output:
    proquest_<dataset-id>.jsonl  — one JSON object per line, fields below.

Output fields per article:
    article_id    SHA-256 hash of url (16 hex chars), stable across runs
    source_id     "proquest_tdm"
    url           original article URL if available, else ProQuest doc ID
    published_at  ISO 8601 UTC (e.g. "2023-03-15T00:00:00Z")
    title         article headline
    body          full text
    author        byline (comma-separated if multiple)
    section       section tag if available
    language      "en" (fixed; Global Newsstream is English-only)
    word_count    whitespace-token count of body

After downloading the JSONL file, place it at:
    data/raw/articles/proquest_<dataset-id>.jsonl
and set PROQUEST_DATASET_ID in .env. See docs/proquest_tdm_setup.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Field name map — TDM Studio document fields vary by client version.
# If title/body come out empty, run `print(list(doc.keys()))` on the first
# document and update the lists below to match.
# ---------------------------------------------------------------------------
_FIELD_MAP = {
    "title":    ["title", "Title"],
    "body":     ["fullText", "FullText", "full_text", "abstract"],
    "pub_date": ["publicationDate", "PublicationDate", "publication_date", "date"],
    "url":      ["url", "URL", "sourceLink", "source_link"],
    "doc_id":   ["id", "documentId", "ProQuestID", "proquest_id"],
    "author":   ["authors", "Authors", "creator", "byline"],
    "section":  ["section", "Section", "sectionHeading", "subject"],
}


def _first(doc: dict, keys: list[str], default: str = "") -> str:
    for k in keys:
        v = doc.get(k)
        if v:
            return str(v) if not isinstance(v, list) else ", ".join(str(x) for x in v)
    return default


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _now_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_date(raw: str) -> str:
    if not raw:
        return _now_utc()
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue
    return _now_utc()


def _doc_to_record(doc: dict) -> dict | None:
    """Convert a TDM Studio document dict to an output record. Returns None if empty."""
    title = _first(doc, _FIELD_MAP["title"])
    body = _first(doc, _FIELD_MAP["body"])
    if not title and not body:
        return None

    url = _first(doc, _FIELD_MAP["url"])
    doc_id = _first(doc, _FIELD_MAP["doc_id"])
    key = url or doc_id or (title + _now_utc())

    return {
        "article_id":   _article_id(key),
        "source_id":    "proquest_tdm",
        "url":          url,
        "published_at": _normalise_date(_first(doc, _FIELD_MAP["pub_date"])),
        "title":        title,
        "body":         body,
        "author":       _first(doc, _FIELD_MAP["author"]) or None,
        "section":      _first(doc, _FIELD_MAP["section"]) or None,
        "language":     "en",
        "word_count":   len(body.split()) if body else 0,
    }


def export_dataset(dataset_id: str, output_path: Path) -> int:
    """Load a TDM Studio dataset and write JSONL to output_path.

    Must run inside the TDM Studio Jupyter environment where proquest_tdm
    is pre-installed. Raises ImportError otherwise.
    """
    try:
        import proquest_tdm as tdm
    except ImportError as exc:
        raise ImportError(
            "proquest_tdm is not installed. This script must run inside the "
            "ProQuest TDM Studio Jupyter environment, not on a local machine."
        ) from exc

    print(f"Loading dataset: {dataset_id}")

    # Authentication is handled automatically by the TDM Studio session.
    # If the client API looks wrong, run `help(tdm)` in the notebook.
    client = tdm.TDMClient()
    dataset = client.get_dataset(dataset_id)

    count = 0
    skipped = 0
    with output_path.open("w", encoding="utf-8") as fh:
        for doc in dataset.documents():
            raw = dict(doc) if not isinstance(doc, dict) else doc
            record = _doc_to_record(raw)
            if record is None:
                skipped += 1
                continue
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
            count += 1
            if count % 500 == 0:
                print(f"  … {count} written", flush=True)

    print(f"Done. {count} articles written, {skipped} skipped → {output_path}")
    return count


if __name__ == "__main__":
    dataset_id = os.environ.get("PROQUEST_DATASET_ID", "").strip()
    if not dataset_id:
        print(
            "Error: PROQUEST_DATASET_ID is not set.\n"
            "Run:  PROQUEST_DATASET_ID=<your-id> python tdm_studio_export.py",
            file=sys.stderr,
        )
        sys.exit(1)

    out = Path(f"proquest_{dataset_id}.jsonl")
    export_dataset(dataset_id, out)
