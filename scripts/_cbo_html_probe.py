"""Throwaway: dump date-bearing markup from one CBO Wayback capture.

The resume probe showed every pid drops with "no page-extracted date" — the
2025/26 captures no longer carry the Drupal dcterms.* meta tags the extractor
matches. This fetches one recent pid's latest capture and prints every <meta>,
JSON-LD block, and <time> element so we can see what date field to match now.

    python scripts/_cbo_html_probe.py [pid]
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from mnd.ingestion.institutional import CBOIngestor

logging.getLogger("mnd").setLevel(logging.INFO)

CKPT = Path("data/raw/articles/.cbo_2010-01-01_2026-06-11_checkpoint.txt")
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 60414
SNAP = "https://web.archive.org/web/{ts}id_/{url}"


def main() -> None:
    ing = CBOIngestor(checkpoint_path=CKPT)
    cdx = ing._build_or_load_cdx_map(date(2010, 1, 1), date(2026, 6, 11))
    earliest_ts, latest_ts = cdx[PID]
    url = f"https://www.cbo.gov/publication/{PID}"
    snap_url = SNAP.format(ts=latest_ts, url=url)
    print(f"\npub/{PID}  latest_ts={latest_ts}  earliest_ts={earliest_ts}")
    print(f"fetch: {snap_url}\n")

    resp = ing._wayback_get(snap_url)
    html = resp.text
    print(f"HTTP {resp.status_code}  |  {len(html)} bytes\n")

    soup = BeautifulSoup(html, "lxml")
    print("===== <title> =====")
    print(f"  {soup.title.string if soup.title else '(none)'}\n")

    print("===== <meta> tags mentioning date/time/published/created/issued =====")
    for m in soup.find_all("meta"):
        attrs = {k: v for k, v in m.attrs.items()}
        blob = " ".join(str(v) for v in attrs.values()).lower()
        if any(t in blob for t in ("date", "time", "publish", "creat", "issued")):
            print(f"  {attrs}")
    print()

    print("===== JSON-LD blocks (datePublished / dateCreated lines) =====")
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = s.string or ""
        for ln in text.splitlines():
            if re.search(r"date(Published|Created|Modified)|datePosted", ln, re.I):
                print(f"  {ln.strip()}")
    print()

    print("===== <time> elements =====")
    for t in soup.find_all("time"):
        print(f"  datetime={t.get('datetime')!r}  text={t.get_text(strip=True)!r}")
    print()

    print("===== any 'datePublished' substring in raw HTML (first 3) =====")
    for m in list(re.finditer(r".{40}datePublished.{60}", html))[:3]:
        print(f"  ...{m.group(0)}...")
    print()


if __name__ == "__main__":
    main()
