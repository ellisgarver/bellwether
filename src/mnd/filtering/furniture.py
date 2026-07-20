"""Per-document structural-furniture cleaning (ADR-082).

Everything the embedder sees should be substance: a useful title plus actual
body prose. Document *furniture* — speaker bylines baked into titles, the
attribution preamble that opens curated speech/interview reprints, PDF page
numbers, running headers/footers, and trailing reference sections — carries no
narrative content, yet it dominates embeddings: the chunker prepends the title
to every chunk, so a byline title ("Jean-Claude Trichet: Interview with FOCUS")
rides on 100% of a document's chunks and clusters documents by speaker and
format rather than by what was said (the register-attachment failure).

Three per-document operations, all reversible-by-metadata:

1. **Byline titles** ("Speaker Name: Real title") are split; the speaker moves
   to the article's ``author`` field (kept when already set) and the title
   keeps the substance. Applied only for sources whose titles carry this
   convention (``byline_sources``) and only with corroborating evidence — the
   same name must appear in the document's opening attribution — so ordinary
   colon titles ("Inflation: the road ahead") pass untouched.
2. **Attribution preambles** — the leading "<Title> Speech/Interview
   by/with Mr X, <office>, at <venue>, <date>." block that curated reprints
   (BIS central-bank speeches) prepend to the prose — are stripped from the
   body start.
3. **PDF furniture** — bare page-number lines, "Page N of M" lines, short
   lines repeated across the same document (running headers/footers), and a
   trailing References/Bibliography section — are dropped line-wise. Raw
   ``pypdf`` extraction keeps all of these inline.

Cross-document repetition is a different failure and stays with the ADR-054
``BoilerplateStripper``; this pass is purely within-document and runs before it.

ACTIVATION IS GATED (``filtering.furniture.enabled``, default false): cleaning
changes chunk text, which changes the ``(chunk_id, text_sha1)`` embedding-cache
key, so affected documents re-embed on the next run. The weekly ``update`` job
is CPU-only (ADR-063) — flipping this on must coincide with a scheduled GPU
re-embed on RCC, never ride silently into the delta job.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from mnd.utils.logging import get_logger

log = get_logger(__name__)

# "Speaker Name: Real title" — 2-4 capitalized name tokens (hyphens/periods/
# apostrophes allowed, e.g. "Jean-Claude Trichet", "William C. Dudley") before
# the first colon. The match is necessary but not sufficient: the same name
# must also appear in the body's opening attribution (double evidence).
_BYLINE_TITLE_RE = re.compile(
    r"^([A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){1,3}):\s+(\S.*)$"
)

# Opening attribution sentence of curated speech/interview reprints:
#   "Speech by Mr Jean-Claude Trichet, President of the European Central
#    Bank, at the ..., Frankfurt, 3 June 2011."
_ATTRIBUTION_KIND = (
    r"(?:speech|interview|remarks|address|statement|keynote(?:\s+\w+)?|"
    r"lecture|welcome\s+address|opening\s+(?:remarks|statement)|"
    r"introductory\s+(?:remarks|statement)|panel\s+(?:remarks|contribution)|"
    r"testimony|presentation|dinner\s+(?:speech|remarks)|text\s+of)"
)
_ATTRIBUTION_RE = re.compile(
    rf"\b{_ATTRIBUTION_KIND}\b[^.]{{0,400}}?\bby\b|"
    rf"\b{_ATTRIBUTION_KIND}\b\s+(?:with|of|in)\b",
    re.IGNORECASE,
)

# A complete date token, in the formats the corpus's CMSs stamp at body start:
# "January 21, 2010", "21 January 2010", "Jan. 21, 2010", "2010-01-21".
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE = (
    rf"(?:{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}"       # January 21, 2010
    rf"|\d{{1,2}}\s+{_MONTH}\.?\s+\d{{4}}"           # 21 January 2010
    rf"|\d{{4}}-\d{{2}}-\d{{2}})"                    # 2010-01-21
)
# Leading publication-date stamp, optionally introduced by "Published[: on]".
_LEADING_DATE_RE = re.compile(
    rf"^\s*(?:published(?:\s+on)?\s*:?\s*)?{_DATE}\b[\s,:.–—-]*",
    re.IGNORECASE,
)
# A bare "Published:" with no date (some CMSs put the date on the next token).
_LEADING_PUBLISHED_RE = re.compile(r"^\s*published(?:\s+on)?\s*:\s*", re.IGNORECASE)
# Leading editorial-credit sentence ("Editors' note: this column first
# appeared…"), stripped to the first sentence boundary, bounded to 300 chars.
_LEADING_CREDIT_RE = re.compile(
    r"^\s*(?:editors?'?\s+note|editor'?s\s+note|author'?s\s+note|"
    r"disclaimer|acknowledgement?s?)\s*[:\-].{0,300}?[.!?]\s+",
    re.IGNORECASE | re.DOTALL,
)

_PAGE_NUMBER_RE = re.compile(r"^\s*(?:-\s*)?\d{1,4}(?:\s*-)?\s*$")
_PAGE_OF_RE = re.compile(r"^\s*page\s+\d+(?:\s+of\s+\d+)?\s*$", re.IGNORECASE)
# Trailing scholarly apparatus — dropped when the heading sits in the document
# tail (last 40%). "References"/"Bibliography" are the citation list; "Notes"/
# "Endnotes"/"Footnotes" the note apparatus. All are furniture with no narrative
# content. NOT "Appendix"/"Annex" (those can carry substantive content).
_REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:references|reference\s+list|bibliography|works\s+cited"
    r"|end\s*notes|foot\s*notes|notes)\s*:?\s*$",
    re.IGNORECASE,
)
# Standalone metadata / citation-apparatus lines, corpus-wide. Each is furniture
# an author or a template placed around the prose, not prose itself: working-
# paper front-matter (JEL, keywords), and citation/retrieval lines. Stripped
# only as a WHOLE line (anchored), so an inline mention is never touched.
_META_LINE_RE = re.compile(
    r"^\s*(?:"
    r"jel\s+(?:classification|codes?|no\.?)\b"
    r"|key\s?words?\s*[:\-]"
    r"|(?:doi|https?|www\.)\S*"
    r"|(?:available|retrieved|downloaded|accessed)\s+(?:at|from|on)\b"
    r"|electronic\s+copy\s+available\s+at\b"
    r"|for\s+(?:media|press)\s+(?:inquiries|enquiries|information)\b"
    r"|\S+@\S+\.\S+\s*$"                       # a bare email-only line
    r")",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


@dataclass
class FurnitureReport:
    """Audit record for one cleaning pass (mirrors ADR-030 fail-loud shape)."""

    n_articles: int = 0
    n_byline_titles_split: int = 0
    n_preambles_stripped: int = 0
    n_leading_stripped: int = 0
    n_furniture_lines_dropped: int = 0
    n_reference_sections_dropped: int = 0
    n_articles_modified: int = 0
    by_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_articles": self.n_articles,
            "n_byline_titles_split": self.n_byline_titles_split,
            "n_leading_stripped": self.n_leading_stripped,
            "n_preambles_stripped": self.n_preambles_stripped,
            "n_furniture_lines_dropped": self.n_furniture_lines_dropped,
            "n_reference_sections_dropped": self.n_reference_sections_dropped,
            "n_articles_modified": self.n_articles_modified,
            "by_source": dict(self.by_source),
        }


def split_byline_title(title: str, body: str) -> tuple[str, str | None]:
    """Split "Speaker Name: Real title" into (real title, speaker).

    Requires double evidence: the prefix must look like a personal name AND the
    same surname must appear within the body's first 400 characters (where the
    attribution sentence sits in curated reprints). Ordinary colon titles
    ("Inflation: the road ahead") and place-name prefixes ("New York: fiscal
    strain") fail the name shape or the guards and pass through unchanged.
    Returns ``(title, None)`` when not a byline.
    """
    m = _BYLINE_TITLE_RE.match(title.strip())
    if not m:
        return title, None
    speaker, rest = m.group(1).strip(), m.group(2).strip()
    tokens = speaker.split()
    lower = [t.lower().strip(".,") for t in tokens]
    # Reject non-name phrases ("Executive Summary:", "Working Paper:") and
    # multi-word place names ("New York:", "Hong Kong:", "South Korea:") — the
    # colon there introduces a subject, not a speaker.
    if any(t in _NON_NAME_TOKENS for t in lower):
        return title, None
    if any(t in _PLACE_TOKENS for t in lower):
        return title, None
    surname = lower[-1]
    if len(surname) < 3:
        return title, None
    if surname not in body[:400].lower():
        return title, None
    return rest, speaker


# Words that disqualify a colon prefix from being a personal name even when
# capitalized ("Executive Summary:", "Press Release:", "Working Paper:").
_NON_NAME_TOKENS = {
    "summary", "release", "paper", "report", "review", "update", "outlook",
    "statement", "minutes", "notes", "brief", "briefing", "chapter", "part",
    "volume", "appendix", "box", "table", "figure", "session", "panel",
    "chart", "special", "focus", "spotlight", "editorial", "commentary",
    "the", "a", "an", "new", "press", "executive", "working", "policy",
    "annual", "quarterly", "monthly", "weekly", "interim", "final",
    "overview", "introduction", "conclusion", "abstract", "highlights",
    "remarks", "speech", "interview", "testimony", "address",
}

# Place tokens that make a capitalized colon-prefix a subject, not a speaker.
# Kept to the multi-word / ambiguous cases the byline regex (2+ tokens) can hit;
# single-word places never match the regex. Mirrors naming.py's proper-noun set.
_PLACE_TOKENS = {
    "new", "york", "hong", "kong", "south", "north", "korea", "sudan", "africa",
    "saudi", "arabia", "puerto", "rico", "united", "states", "kingdom", "nations",
    "middle", "east", "latin", "america", "european", "union", "euro", "area",
    "san", "francisco", "los", "angeles", "el", "salvador", "sri", "lanka",
    "costa", "rica", "sierra", "leone", "cape", "verde", "ivory", "coast",
    "czech", "republic", "central", "western", "eastern", "southern", "northern",
    "sub", "saharan", "asia", "pacific", "atlantic", "mediterranean", "gulf",
}


def strip_leading_furniture(body: str, title: str) -> tuple[str, bool]:
    """Strip leading furniture from a body head — corpus-wide, newline-agnostic.

    Web and PDF extractions often produce a single-line body whose head is CMS
    furniture the line-based pass cannot reach. Removed, in order, from the very
    start only:
      1. a verbatim repeat of the document title (many CMSs prepend it);
      2. a leading publication-date stamp ("January 21, 2010", "2010-01-21"),
         optionally introduced by "Published:" — the corpus's most common lead
         furniture (e.g. 1.5k CBO cost-estimate bodies open "January 21, 2010
         Cost Estimate …");
      3. a leading editorial-credit sentence ("Editors' note: …", "Disclaimer: …")
         to the first sentence boundary, bounded to ~300 chars.

    Each step is anchored at position 0, so an inline date or an inline "note:"
    is never touched. Returns ``(cleaned_body, changed)``.
    """
    original = body
    text = body.lstrip()
    # 1. verbatim leading title repeat (only an exact prefix match — a real
    #    opening sentence does not equal the whole title then continue).
    t = title.strip()
    if t and len(t) >= 8 and text[: len(t)].lower() == t.lower():
        text = text[len(t):].lstrip(" \t\n:—–-.")
    # 2. leading date stamp / "Published:" + date, then a bare "Published:".
    text = _LEADING_DATE_RE.sub("", text, count=1)
    text = _LEADING_PUBLISHED_RE.sub("", text, count=1)
    # 3. leading editorial-credit sentence.
    text = _LEADING_CREDIT_RE.sub("", text, count=1)
    text = text.lstrip()
    return (text, True) if text and text != original.lstrip() else (original, False)


def strip_attribution_preamble(body: str, title: str) -> tuple[str, bool]:
    """Remove the leading reprint header: repeated title + attribution sentence.

    Curated speech/interview reprints open with the document title itself and
    then an attribution sentence ("Interview with Mr X, President of the ...,
    in <outlet>, conducted by ..., <date>."). Both precede the actual prose
    and both are removed; the cut never extends past the first 600 characters,
    so a false positive costs at most the document's opening line.
    """
    original = body
    text = body.lstrip()
    # 1. The body often opens with the (byline) title verbatim.
    t = title.strip()
    if t and text[: len(t) + 8].lower().startswith(t.lower()):
        text = text[len(t):].lstrip(" \t\n:—–-")
    # 2. The attribution sentence, when it opens the remaining text.
    head = text[:600]
    m = _ATTRIBUTION_RE.search(head)
    if m is not None and m.start() < 120:
        # Cut to the end of the attribution sentence: the first period that is
        # followed by whitespace + an uppercase letter (sentence boundary), at
        # or after the match — dates like "3 June 2011." end the header.
        boundary = re.search(r"\.\s+(?=[A-Z*“\"(])", text[m.start():600 + 200])
        if boundary is not None:
            text = text[m.start() + boundary.end():].lstrip()
            return text, True
    return (text, True) if text != original.lstrip() else (original, False)


def strip_body_furniture(
    body: str,
    *,
    max_running_line_words: int = 6,
    min_repeats_running_line: int = 3,
    strip_reference_sections: bool = True,
    strip_metadata_lines: bool = True,
) -> tuple[str, int, bool]:
    """Drop line-level furniture from a document body — corpus-wide, not PDF-only.

    Within-document and line-based, so it applies to every source's body (PDF
    extractions carry the most, but web extractions carry residual nav/footer
    lines too). Removes, per line:
      - bare page numbers and "Page N of M" lines;
      - *running lines* — short lines (<= ``max_running_line_words`` words) whose
        normalized form repeats >= ``min_repeats_running_line`` times in the same
        document, the signature of a header/footer printed on every page;
      - standalone metadata / citation-apparatus lines (JEL, keywords, DOI/URL,
        "Available at", media-contact, bare email) when ``strip_metadata_lines``;
      - a trailing References/Notes section when its heading sits in the tail.

    Only whole-line matches are removed, so inline mentions are never touched.
    Returns ``(cleaned_body, n_lines_dropped, trailing_section_dropped)``.
    """
    lines = body.split("\n")
    if len(lines) < 4:
        return body, 0, False

    norm = [_WHITESPACE.sub(" ", ln).strip().lower() for ln in lines]
    short_counts = Counter(
        n for n, ln in zip(norm, lines)
        if n and len(n.split()) <= max_running_line_words
    )
    running = {
        n for n, c in short_counts.items() if c >= min_repeats_running_line
    }

    kept: list[str] = []
    dropped = 0
    ref_dropped = False
    cutoff = int(len(lines) * 0.6)
    for i, (ln, n) in enumerate(zip(lines, norm)):
        if strip_reference_sections and i >= cutoff and _REFERENCE_HEADING_RE.match(ln):
            dropped += len(lines) - i
            ref_dropped = True
            break
        if (
            _PAGE_NUMBER_RE.match(ln)
            or _PAGE_OF_RE.match(ln)
            or (n in running)
            or (strip_metadata_lines and _META_LINE_RE.match(ln))
        ):
            dropped += 1
            continue
        kept.append(ln)
    if dropped == 0:
        return body, 0, False
    return "\n".join(kept), dropped, ref_dropped


# Back-compat alias (the PDF-only name predated the corpus-wide generalization).
strip_pdf_furniture = strip_body_furniture


class FurnitureCleaner:
    """Config-driven per-document furniture cleaning pass (ADR-082)."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        byline_sources: tuple[str, ...] = ("bis",),
        max_running_line_words: int = 6,
        min_repeats_running_line: int = 3,
        strip_reference_sections: bool = True,
        strip_metadata_lines: bool = True,
    ) -> None:
        self.enabled = enabled
        self.byline_sources = set(byline_sources)
        self.max_running_line_words = max_running_line_words
        self.min_repeats_running_line = min_repeats_running_line
        self.strip_reference_sections = strip_reference_sections
        self.strip_metadata_lines = strip_metadata_lines
        self.report = FurnitureReport()

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "FurnitureCleaner":
        fc = ((cfg.get("filtering") or {}).get("furniture") or {})
        return cls(
            enabled=bool(fc.get("enabled", False)),
            byline_sources=tuple(fc.get("byline_sources", ["bis"])),
            max_running_line_words=int(fc.get("max_running_line_words", 6)),
            min_repeats_running_line=int(fc.get("min_repeats_running_line", 3)),
            strip_reference_sections=bool(fc.get("strip_reference_sections", True)),
            strip_metadata_lines=bool(fc.get("strip_metadata_lines", True)),
        )

    def clean_one(self, title: str, body: str, source: str, author: Any = None):
        """Clean one document's (title, body); return (title, body, speaker, report_deltas).

        Pure — mutates nothing — so the audit script can preview effects without
        touching the corpus. ``report_deltas`` is a dict of the per-document
        counts the aggregate report accumulates.
        """
        deltas = {"byline": 0, "preamble": 0, "leading": 0,
                  "furniture_lines": 0, "reference": 0}
        speaker = None
        if source in self.byline_sources:
            new_title, spk = split_byline_title(title, body)
            if spk is not None:
                title, speaker = new_title, spk
                deltas["byline"] = 1
            new_body, stripped = strip_attribution_preamble(body, title)
            if stripped:
                body = new_body
                deltas["preamble"] = 1
        # Corpus-wide leading furniture (title repeat, date stamp, credit line).
        new_body, led = strip_leading_furniture(body, title)
        if led:
            body = new_body
            deltas["leading"] = 1
        new_body, n_dropped, ref_dropped = strip_body_furniture(
            body,
            max_running_line_words=self.max_running_line_words,
            min_repeats_running_line=self.min_repeats_running_line,
            strip_reference_sections=self.strip_reference_sections,
            strip_metadata_lines=self.strip_metadata_lines,
        )
        if n_dropped:
            body = new_body
            deltas["furniture_lines"] = n_dropped
            deltas["reference"] = int(ref_dropped)
        return title, body, speaker, deltas

    def clean(self, articles: list[Any]) -> list[Any]:
        """Clean titles/bodies in place; backfill ``author`` from split bylines."""
        rep = FurnitureReport(n_articles=len(articles))
        for a in articles:
            title = str(getattr(a, "title", "") or "")
            body = str(getattr(a, "body", "") or "")
            source = str(getattr(a, "source_id", "") or "")
            new_title, new_body, speaker, d = self.clean_one(title, body, source)
            if speaker is not None:
                a.title = new_title
                if not getattr(a, "author", None):
                    a.author = speaker
                rep.n_byline_titles_split += 1
                rep.by_source[source] = rep.by_source.get(source, 0) + 1
            rep.n_preambles_stripped += d["preamble"]
            rep.n_leading_stripped += d["leading"]
            rep.n_furniture_lines_dropped += d["furniture_lines"]
            rep.n_reference_sections_dropped += d["reference"]
            if speaker is not None or d["preamble"] or d["leading"] or d["furniture_lines"]:
                a.body = new_body
                rep.n_articles_modified += 1
        self.report = rep
        return articles
