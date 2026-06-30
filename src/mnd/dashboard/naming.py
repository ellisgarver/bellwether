"""Display-layer narrative naming (ADR-056).

Turns each surfaced cluster's existing representation — the ADR-055 c-TF-IDF
terms plus its BERTopic representative-document excerpts, and its date span and
source mix — into a short human-readable title and a one-line description via a
paid LLM. This replaces BERTopic's default underscore-joined label
(``23_nps_lands_acres_park``) at the *display* layer only.

The name never feeds embedding, clustering, JEL scope, fitting, staging, or
anchor recovery: the no-paid-dependency rule binds the data-fetching and analysis
pipeline, and the presentation layer is exempt (CLAUDE.md). Reproducibility is
preserved by caching each title under a content hash of its representation and
committing the cache (``display.naming.cache_dir``, a tracked path): a bake reuses
every unchanged cluster's title and only calls the model for new or changed
clusters, so the static site rebuilds deterministically with no API key. The
feature degrades to absent — the front end falls back to the c-TF-IDF label —
when naming is disabled or no Anthropic client can be built, exactly like the
markets (ADR-047) and Media Cloud (ADR-048) overlays.

The model call is synchronous (one short Messages request per cache miss,
``temperature=0`` for stability, a JSON-schema structured output). The committed
cache makes each bake incremental, so the Batches API's throughput is unnecessary
here; it remains a drop-in option if a cold full-corpus naming pass ever matters.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mnd.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class NamingInput:
    """The frozen representation a title is generated from (mirrors JEL's, ADR-055)."""

    cluster_id: int
    terms: list[str]
    excerpts: list[str]
    date_range: tuple[str, str] | None = None
    sources: list[str] = field(default_factory=list)  # top source ids, most frequent first


@dataclass(frozen=True)
class NarrativeName:
    title: str
    description: str


# System prompt is part of the cache key (via prompt_version) — changing it
# without bumping display.naming.prompt_version would silently reuse stale titles.
_SYSTEM = (
    "You name clusters of economic-policy and financial writing for a public, "
    "educational dashboard. You are given a cluster's keywords and short excerpts "
    "from its most representative documents. Write a concise, neutral name and a "
    "one-sentence description of what the cluster is about. Use ONLY the supplied "
    "material: no outside knowledge, and no events, places, or dates that are not "
    "present in the text. If the material is not about economics or finance, name "
    "it plainly for what it actually is rather than forcing an economic framing. "
    "No sensational or editorial language. Return strictly the requested JSON."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "description"],
    "additionalProperties": False,
}


def _build_user(inp: NamingInput, max_title_words: int) -> str:
    """Render one cluster's representation into the user message."""
    lines = [f"Keywords: {', '.join(inp.terms[:15])}"]
    if inp.sources:
        lines.append(f"Sources: {', '.join(inp.sources[:4])}")
    if inp.date_range:
        lines.append(f"Active: {inp.date_range[0]} to {inp.date_range[1]}")
    lines.append("Representative excerpts:")
    for i, ex in enumerate(inp.excerpts[:3], 1):
        lines.append(f"{i}. {ex.strip()[:400]}")
    lines.append(
        f"\nReturn JSON with: title (a noun phrase of at most {max_title_words} "
        "words, no trailing period) and description (one sentence, at most 25 words)."
    )
    return "\n".join(lines)


def _signature(
    inp: NamingInput, model: str, prompt_version: int, max_title_words: int
) -> str:
    """Content hash of everything that determines the generated title.

    Keyed on the representation (terms, excerpts, sources, dates) plus the model,
    prompt version, and title-length knob, so any representation change OR any
    prompt/model change yields a new key and invalidates a stale cache entry.
    """
    payload = json.dumps(
        {
            "t": inp.terms,
            "e": inp.excerpts,
            "s": list(inp.sources),
            "d": inp.date_range,
            "m": model,
            "v": prompt_version,
            "w": max_title_words,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


class _LLMClient(Protocol):
    """Minimal interface; the production impl is ``AnthropicNamer``, tests inject a stub."""

    def name_cluster(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class AnthropicNamer:
    """Production naming client: Claude Haiku via the Messages API (ADR-056).

    Lazily imports ``anthropic`` and resolves the key from the environment so the
    package imports without the dependency or a key configured; a missing key
    surfaces when the client is constructed, which the caller treats as "naming
    absent" and falls back to the c-TF-IDF label.
    """

    def __init__(self, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "AnthropicNamer":
        model = ((cfg.get("display") or {}).get("naming") or {}).get(
            "model", "claude-haiku-4-5"
        )
        return cls(model)

    def name_cluster(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)


def generate_names(
    inputs: list[NamingInput],
    cfg: dict[str, Any],
    *,
    client: _LLMClient | None = None,
) -> dict[int, NarrativeName]:
    """Resolve a human title + description per cluster, cache-incremental (ADR-056).

    Returns ``cluster_id -> NarrativeName`` for every cluster a name could be
    resolved for (from cache or freshly generated); clusters with no name keep
    their c-TF-IDF label downstream. Returns ``{}`` (all fall back) when naming is
    disabled or no client can be built. ``client`` is injectable for tests; in
    production it is constructed lazily, only on a cache miss.
    """
    nc = (cfg.get("display") or {}).get("naming") or {}
    if not nc.get("enabled", False):
        log.info(
            "Narrative naming disabled (display.naming.enabled=false); "
            "front end uses c-TF-IDF labels"
        )
        return {}

    model = str(nc.get("model", "claude-haiku-4-5"))
    prompt_version = int(nc.get("prompt_version", 1))
    max_title_words = int(nc.get("max_title_words", 6))
    cache_dir = Path(nc.get("cache_dir", "data/naming_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)

    out: dict[int, NarrativeName] = {}
    misses: list[tuple[NamingInput, Path]] = []
    for inp in inputs:
        sig = _signature(inp, model, prompt_version, max_title_words)
        path = cache_dir / f"name_{inp.cluster_id}_{sig}.json"
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                out[inp.cluster_id] = NarrativeName(d["title"], d["description"])
                continue
            except Exception as exc:  # partial/corrupt write — regenerate this one
                log.warning(
                    "Naming cache unreadable for cluster %s (%s); regenerating",
                    inp.cluster_id, exc,
                )
        misses.append((inp, path))

    n_cached = len(out)
    if misses:
        if client is None:
            try:
                client = AnthropicNamer.from_config(cfg)
            except Exception as exc:
                log.warning(
                    "Narrative naming skipped — no Anthropic client (%s); %d clusters "
                    "keep c-TF-IDF labels (%d served from cache)",
                    exc, len(misses), n_cached,
                )
                return out
        produced_any = False
        for inp, path in misses:
            try:
                d = client.name_cluster(_SYSTEM, _build_user(inp, max_title_words), _SCHEMA)
                name = NarrativeName(str(d["title"]).strip(), str(d["description"]).strip())
            except Exception as exc:
                log.warning("Naming failed for cluster %s: %s", inp.cluster_id, exc)
                if not produced_any:
                    # First call failed → almost certainly systemic (missing key, SDK,
                    # rate ceiling), not a one-off bad cluster. Abort rather than fire
                    # the same failing call for every remaining cluster; they keep
                    # their c-TF-IDF labels.
                    log.warning(
                        "Narrative naming aborted after the first failure (likely "
                        "auth/config); %d clusters keep c-TF-IDF labels", len(misses),
                    )
                    break
                continue
            produced_any = True
            out[inp.cluster_id] = name
            path.write_text(
                json.dumps(
                    {"title": name.title, "description": name.description},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    log.info(
        "Narrative names: %d resolved (%d from cache, %d freshly generated) → %s",
        len(out), n_cached, len(out) - n_cached, cache_dir,
    )
    return out
