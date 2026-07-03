"""Per-cluster extractive story card (ADR-039 companion).

For each narrative (BERTopic topic) the dashboard renders a "story card": a
compact, human-readable summary assembled from **real article material** — top
c-TF-IDF terms, representative article titles + excerpts, the source mix, the
date span, and the peak day. It is the unit the life-cycle view hangs its
SIR/logistic/Bass/shape-facts panels and the Media Cloud / markets overlays off.

This builder is deliberately **extractive only** — no LLM, no generated prose.
Representative articles are chosen by term overlap with the cluster's own
c-TF-IDF terms and excerpts are sliced verbatim from article bodies. That keeps
the card inside the no-paid-dep core (paid-AI narrative prose is a deferred
display-layer add-on, exempt from the core rule but not built here).

Inputs are the persisted clustering artifacts:
    clusters.parquet   — one row per chunk, with the per-chunk `topic` column and
                         the carried-through Article fields (article_id,
                         source_id, url, published_at, title, body, chunk_index…)
    topic_info.parquet — BERTopic get_topic_info(): Topic, Count, Name,
                         Representation (top terms), Representative_Docs.

Noise (topic == -1) is skipped.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from mnd.utils.logging import get_logger

log = get_logger(__name__)

NOISE_TOPIC = -1


@dataclass
class StoryCard:
    cluster_id: int
    label: str
    top_terms: list[str] = field(default_factory=list)
    n_articles: int = 0
    n_chunks: int = 0
    date_range: tuple[str, str] | None = None
    peak_date: str | None = None
    source_mix: list[tuple[str, int]] = field(default_factory=list)
    # Three complementary representative-article panels (ADR-061): the narrative's
    # own story — how it entered, where it stands now, and its most central pieces.
    # ``central_articles`` (most aligned + substantial) also grounds the naming
    # layer. ``representative_articles`` aliases ``central_articles`` for back-compat.
    earliest_articles: list[dict[str, Any]] = field(default_factory=list)
    newest_articles: list[dict[str, Any]] = field(default_factory=list)
    central_articles: list[dict[str, Any]] = field(default_factory=list)
    representative_articles: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _published_day(value: Any) -> str | None:
    """Take the YYYY-MM-DD prefix of an ISO published_at value."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value)
    return s[:10] if len(s) >= 10 else None


def _terms_from_topic_info(topic_info: pd.DataFrame | None, cluster_id: int) -> tuple[str, list[str]]:
    """Return (label, top_terms) for a topic from a BERTopic get_topic_info frame."""
    if topic_info is None or "Topic" not in topic_info.columns:
        return f"Cluster {cluster_id}", []
    row = topic_info.loc[topic_info["Topic"] == cluster_id]
    if row.empty:
        return f"Cluster {cluster_id}", []
    r = row.iloc[0]
    label = str(r["Name"]) if "Name" in row.columns and pd.notna(r["Name"]) else f"Cluster {cluster_id}"
    terms: list[str] = []
    if "Representation" in row.columns:
        rep = r["Representation"]
        # Parquet round-trips BERTopic's Representation list into a numpy ndarray,
        # which matches neither the list/tuple nor the str branch, leaving terms
        # empty and pushing every cluster to JEL "Y" (out of scope). tolist()
        # normalizes any array-like (ndarray, pandas extension array) to a list.
        if hasattr(rep, "tolist"):
            rep = rep.tolist()
        if isinstance(rep, (list, tuple)):
            terms = [str(t).strip() for t in rep if str(t).strip()]
        elif isinstance(rep, str) and rep.strip():
            terms = [t.strip() for t in re.split(r"[,\s]+", rep) if t.strip()]
    if not terms and label != f"Cluster {cluster_id}":
        # Fall back to BERTopic's Name ("<id>_term_term_term"): drop the leading
        # numeric topic id and keep the keyword stems.
        parts = label.split("_")
        if parts and parts[0].lstrip("-").isdigit():
            parts = parts[1:]
        terms = [p for p in parts if p.strip()]
    return label, terms


def _representative_docs_from_topic_info(
    topic_info: pd.DataFrame | None, cluster_id: int, n_docs: int = 3, *, max_chars: int = 320
) -> list[str]:
    """Return up to ``n_docs`` BERTopic representative-document excerpts for a topic.

    Enriches the JEL classifier's cluster representation (ADR-055): c-TF-IDF terms
    alone are a thin signal, and pairing them with representative-document text
    sharpens the nearest-prototype assignment. Each document is cut to a leading
    ``max_chars`` excerpt. As in ``_terms_from_topic_info``, parquet round-trips
    the ``Representative_Docs`` list into a numpy ndarray, normalized via tolist().
    """
    if (
        topic_info is None
        or "Topic" not in topic_info.columns
        or "Representative_Docs" not in topic_info.columns
    ):
        return []
    row = topic_info.loc[topic_info["Topic"] == cluster_id]
    if row.empty:
        return []
    docs = row.iloc[0]["Representative_Docs"]
    if hasattr(docs, "tolist"):
        docs = docs.tolist()
    if not isinstance(docs, (list, tuple)):
        return []
    excerpts = [_excerpt(str(d), max_chars) for d in docs[:n_docs]]
    return [e for e in excerpts if e]


def _score_by_terms(text: str, terms: list[str]) -> int:
    """Count total occurrences of the cluster's top terms in an article's text."""
    if not terms:
        return 0
    low = text.lower()
    return sum(low.count(t.lower()) for t in terms)


def _excerpt(text: str, max_chars: int) -> str:
    """Verbatim leading slice of an article body, cut on a word boundary."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def build_story_card(
    cluster_id: int,
    clusters_df: pd.DataFrame,
    topic_info: pd.DataFrame | None = None,
    *,
    n_terms: int = 10,
    n_per_bucket: int = 3,
    n_sources: int = 8,
    excerpt_chars: int = 320,
) -> StoryCard:
    """Assemble the extractive story card for one cluster (topic).

    Chunk rows are folded back to articles on ``article_id`` (chunks of a long
    document share one id); each article's full text is the concatenation of its
    chunk bodies, with metadata taken from its first chunk. Three de-duplicated
    representative-article panels are surfaced (ADR-061), ``n_per_bucket`` each:
    the most *central* (aligned with the narrative's terms + most substantial —
    these also ground naming), the *earliest*, and the *newest*.
    """
    rows = clusters_df[clusters_df["topic"] == cluster_id]
    label, all_terms = _terms_from_topic_info(topic_info, cluster_id)
    top_terms = all_terms[:n_terms]

    card = StoryCard(cluster_id=int(cluster_id), label=label, top_terms=top_terms)
    if rows.empty:
        return card

    card.n_chunks = int(len(rows))

    # Fold chunks → articles.
    articles: list[dict[str, Any]] = []
    sort_col = "chunk_index" if "chunk_index" in rows.columns else None
    for article_id, grp in rows.groupby("article_id", sort=False):
        if sort_col:
            grp = grp.sort_values(sort_col)
        head = grp.iloc[0]
        full_text = " ".join(str(b) for b in grp.get("body", pd.Series([], dtype=str)).fillna(""))
        articles.append(
            {
                "article_id": str(article_id),
                "title": str(head.get("title", "") or ""),
                "source_id": str(head.get("source_id", "") or ""),
                "url": str(head.get("url", "") or ""),
                "published_at": head.get("published_at"),
                "published_day": _published_day(head.get("published_at")),
                "_full_text": full_text,
            }
        )

    card.n_articles = len(articles)

    # Source mix (article-level), most common first.
    src_counts = Counter(a["source_id"] for a in articles if a["source_id"])
    card.source_mix = src_counts.most_common(n_sources)

    # Date span + peak day (article-level counts).
    days = sorted(a["published_day"] for a in articles if a["published_day"])
    if days:
        card.date_range = (days[0], days[-1])
        card.peak_date = Counter(days).most_common(1)[0][0]

    # Three complementary panels (ADR-061), de-duplicated so a document never
    # appears twice. Central articles (most term-aligned, then most substantial by
    # length, then newest) are the narrative's core and ground the naming layer;
    # earliest and newest bracket its lifecycle.
    for a in articles:
        a["_score"] = _score_by_terms(a["title"] + " " + a["_full_text"], top_terms)

    def _view(a: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": a["title"],
            "source_id": a["source_id"],
            "url": a["url"],
            "published_at": a["published_at"],
            "excerpt": _excerpt(a["_full_text"], excerpt_chars),
            "term_overlap": a["_score"],
        }

    central = sorted(
        articles,
        key=lambda a: (a["_score"], len(a["_full_text"]), a["published_day"] or ""),
        reverse=True,
    )[:n_per_bucket]
    seen = {a["article_id"] for a in central}
    card.central_articles = [_view(a) for a in central]

    dated = [a for a in articles if a["published_day"]]
    earliest = [a for a in sorted(dated, key=lambda a: a["published_day"]) if a["article_id"] not in seen][:n_per_bucket]
    seen |= {a["article_id"] for a in earliest}
    card.earliest_articles = [_view(a) for a in earliest]

    newest = [a for a in sorted(dated, key=lambda a: a["published_day"], reverse=True) if a["article_id"] not in seen][:n_per_bucket]
    card.newest_articles = [_view(a) for a in newest]

    card.representative_articles = card.central_articles  # back-compat alias
    return card


def build_all_cards(
    clusters_df: pd.DataFrame,
    topic_info: pd.DataFrame | None = None,
    **kwargs: Any,
) -> list[StoryCard]:
    """Build a story card for every non-noise topic, largest cluster first."""
    topics = [int(t) for t in clusters_df["topic"].unique() if int(t) != NOISE_TOPIC]
    cards = [build_story_card(t, clusters_df, topic_info, **kwargs) for t in topics]
    cards.sort(key=lambda c: c.n_articles, reverse=True)
    return cards
