"""Sub-document boilerplate removal (ADR-054).

Whole-document near-duplicate removal (``dedup.Deduplicator``, ADR-019) drops
articles that are duplicates in their entirety. It cannot catch a disclaimer,
donation disclosure, media-contact block, or speech caveat repeated verbatim
*inside* otherwise-distinct documents. Such passages are lexically identical
across hundreds of documents, dominate the c-TF-IDF signal, and produce artifact
clusters keyed on the boilerplate rather than the macro content.

This module removes that repetition at the filter stage, after MinHash dedup and
before the corpus is embedded. The criterion is mechanical and topic-blind: a
normalized sentence appearing in at least ``min_doc_frequency`` distinct documents
is template text and is stripped from every document. Real macro prose carries
document-specific numbers, dates, and entities, so its exact normalized form
rarely recurs across many documents; only invariant template text crosses the
threshold. This is the template-detection criterion of Bar-Yossef & Rajagopalan
(2002) and the boilerplate-removal lineage of Kohlschütter et al. (2010), and is
the sub-document analogue of the Broder (1997) / Henzinger (2006) whole-document
dedup. Document count, never topic, is the only input, so the ADR-020 prohibition
on a pre-cluster topical filter is untouched.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

from mnd.ingestion.base import Article

# Reporting cap — number of top boilerplate sentences enumerated in the report.
_REPORT_TOP_K = 50

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"\s+")
_EDGE_NONWORD = re.compile(r"^\W+|\W+$")


def _split_sentences(text: str) -> list[str]:
    """Split body text into sentence-like segments, keeping terminal punctuation."""
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT.split(text.strip())) if s]


def _normalize(sentence: str) -> str:
    """Match key for a sentence: lowercase, whitespace-collapsed, edges trimmed."""
    collapsed = _WHITESPACE.sub(" ", sentence.lower()).strip()
    return _EDGE_NONWORD.sub("", collapsed)


@dataclass
class BoilerplateReport:
    """Audit record for one strip pass (ADR-030 fail-loud)."""

    n_boilerplate_sentences: int = 0
    n_instances_removed: int = 0
    n_articles_modified: int = 0
    n_articles_dropped: int = 0
    dropped_article_ids: list[str] = field(default_factory=list)
    top_boilerplate: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_boilerplate_sentences": self.n_boilerplate_sentences,
            "n_instances_removed": self.n_instances_removed,
            "n_articles_modified": self.n_articles_modified,
            "n_articles_dropped": self.n_articles_dropped,
            "dropped_article_ids": self.dropped_article_ids,
            "top_boilerplate": self.top_boilerplate,
        }


class BoilerplateStripper:
    """Remove cross-document recurring passages from article bodies.

    A two-pass corpus operation: pass one counts the distinct-document frequency
    of every eligible normalized sentence; pass two removes the high-frequency
    sentences from each body, mutating ``body`` and ``word_count`` in place and
    dropping articles reduced to content-free shells.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        min_doc_frequency: int = 25,
        min_sentence_words: int = 6,
        min_content_words: int = 50,
    ) -> None:
        self.enabled = enabled
        self.min_doc_frequency = min_doc_frequency
        self.min_sentence_words = min_sentence_words
        self.min_content_words = min_content_words
        self.report = BoilerplateReport()

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "BoilerplateStripper":
        bp = ((cfg.get("filtering") or {}).get("boilerplate") or {})
        return cls(
            enabled=bool(bp.get("enabled", True)),
            min_doc_frequency=int(bp.get("min_doc_frequency", 25)),
            min_sentence_words=int(bp.get("min_sentence_words", 6)),
            min_content_words=int(bp.get("min_content_words", 50)),
        )

    def _eligible(self, sentence: str) -> bool:
        return len(sentence.split()) >= self.min_sentence_words

    def strip(self, articles: Sequence[Article]) -> list[Article]:
        """Return the corpus with boilerplate sentences removed.

        Articles are mutated in place. Records reduced below ``min_content_words``
        by the strip are dropped; records from which nothing was removed are kept
        unchanged regardless of length (a naturally short clean article is not a
        boilerplate shell).
        """
        if not self.enabled:
            self.report = BoilerplateReport()
            return list(articles)

        sentences_by_article = [_split_sentences(a.body or "") for a in articles]

        doc_frequency: Counter[str] = Counter()
        for sentences in sentences_by_article:
            seen: set[str] = set()
            for sentence in sentences:
                if not self._eligible(sentence):
                    continue
                key = _normalize(sentence)
                if key and key not in seen:
                    seen.add(key)
                    doc_frequency[key] += 1

        boilerplate = {k for k, n in doc_frequency.items() if n >= self.min_doc_frequency}

        kept: list[Article] = []
        instances_removed = 0
        n_modified = 0
        dropped_ids: list[str] = []

        for article, sentences in zip(articles, sentences_by_article):
            survivors: list[str] = []
            removed_here = 0
            for sentence in sentences:
                if self._eligible(sentence) and _normalize(sentence) in boilerplate:
                    removed_here += 1
                else:
                    survivors.append(sentence)

            if removed_here == 0:
                kept.append(article)
                continue

            instances_removed += removed_here
            new_body = " ".join(survivors).strip()
            content_words = len(new_body.split())
            if content_words < self.min_content_words:
                dropped_ids.append(article.article_id)
                continue

            article.body = new_body
            article.word_count = content_words
            n_modified += 1
            kept.append(article)

        top = sorted(boilerplate, key=lambda k: doc_frequency[k], reverse=True)[:_REPORT_TOP_K]
        self.report = BoilerplateReport(
            n_boilerplate_sentences=len(boilerplate),
            n_instances_removed=instances_removed,
            n_articles_modified=n_modified,
            n_articles_dropped=len(dropped_ids),
            dropped_article_ids=dropped_ids,
            top_boilerplate=[{"text": k[:200], "doc_frequency": doc_frequency[k]} for k in top],
        )
        return kept
