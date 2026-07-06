"""Display-layer narrative naming (ADR-056).

Turns each surfaced cluster's existing representation — the ADR-055 c-TF-IDF
terms plus its BERTopic representative-document excerpts, and its date span and
source mix — into a short human-readable title and a one-line description via an
LLM. This replaces BERTopic's default underscore-joined label
(``23_nps_lands_acres_park``) at the *display* layer only.

Default backend is an **open Llama** via an OpenAI-compatible endpoint (ADR-067),
so the whole pipeline is key-free and reproducible — a local Ollama out of the box,
or any hosted OpenAI-compatible URL. A paid Anthropic backend and an in-process
transformers backend remain selectable via ``display.naming.backend``.

The name never feeds embedding, clustering, JEL scope, fitting, staging, or
anchor recovery (display layer only; ADR-056). Reproducibility is preserved by
caching each title under a content hash of its representation and committing the
cache (``display.naming.cache_dir``, a tracked path): a bake reuses every unchanged
cluster's title and only calls the model for new or changed clusters, so the static
site rebuilds deterministically. The feature degrades to absent — the front end
falls back to the c-TF-IDF label — when naming is disabled or no client can be
reached, exactly like the markets (ADR-047) and Media Cloud (ADR-048) overlays.

Each call is synchronous (one short request per cache miss, ``temperature=0`` for
determinism, a JSON object response). The committed cache makes each bake
incremental.
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
    "You write titles and descriptions for clusters of U.S. economic-policy and "
    "financial writing, shown on a public educational dashboard that tracks how such "
    "narratives rise and fade. You are given a cluster's defining keywords and short "
    "excerpts from its most central documents.\n\n"
    "Write two things:\n"
    "- title: a short, specific noun phrase naming what the cluster is about — a "
    "headline, not a sentence, and not a bare keyword. Name the period or event when "
    "the excerpts make it clear.\n"
    "- description: 3 to 4 plain, concrete sentences explaining what the narrative is "
    "about and why it mattered, written for an interested non-expert.\n\n"
    "Rules:\n"
    "- Use ONLY the supplied keywords and excerpts. Do not add events, places, dates, "
    "numbers, or claims that are not present in them; when unsure, stay general.\n"
    "- If the material is not about economics or finance, name it plainly for what it "
    "actually is rather than forcing an economic framing.\n"
    "- Neutral and factual: no hype, no editorializing, no forecasting, no advice.\n"
    "- Do not open with filler such as 'This narrative', 'This cluster', 'This topic', "
    "'In the world of', or 'Explores' — start with the substance, and vary how you "
    "open across descriptions.\n"
    "Return strictly the requested JSON."
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


def _build_user(inp: NamingInput, title_words: int) -> str:
    """Render one cluster's representation into the user message."""
    lines = [f"Keywords: {', '.join(inp.terms[:15])}"]
    if inp.sources:
        lines.append(f"Sources: {', '.join(inp.sources[:4])}")
    if inp.date_range:
        lines.append(f"Active: {inp.date_range[0]} to {inp.date_range[1]}")
    lines.append("Central excerpts:")
    for i, ex in enumerate(inp.excerpts[:3], 1):
        lines.append(f"{i}. {ex.strip()[:500]}")
    lines.append(
        "\nReturn JSON with two keys: title (a short, specific phrase — roughly "
        f"{title_words} words, never a full sentence, no trailing period) and "
        "description (3 to 4 plain, concrete sentences)."
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
            max_tokens=512,           # room for a 3-4 sentence description
            temperature=0,            # deterministic → the committed cache is meaningful
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)


def _parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from free-form model output.

    Open models are not schema-constrained, so they may wrap the JSON in prose or
    a code fence. Slice from the first ``{`` to the last ``}`` and parse.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON object in model output: {text[:120]!r}")
    return json.loads(text[start : end + 1])


class LocalHFNamer:
    """Open-source naming client: a local instruction-tuned model via transformers.

    Keeps the whole pipeline free and reproducible (no paid API, no key) — the
    naming task is short grounded generation, well within a 7B instruct model. Greedy
    decoding (no sampling) is the temperature-0 equivalent, so a re-bake is
    deterministic and the committed cache stays meaningful. Heavier than the paid
    path (a multi-GB model + GPU for reasonable speed), so it is opt-in via
    ``display.naming.backend: local``; both are exposed for the ADR-056 A/B.
    """

    def __init__(self, model_id: str) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype="auto", device_map="auto"
        )
        self._model_id = model_id

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "LocalHFNamer":
        nc = ((cfg.get("display") or {}).get("naming") or {})
        return cls(str(nc.get("local_model", "Qwen/Qwen2.5-7B-Instruct")))

    def name_cluster(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user + '\n\nRespond with only a JSON object: {"title": ..., "description": ...}',
            },
        ]
        prompt = self._tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        out = self._model.generate(**inputs, max_new_tokens=512, do_sample=False)
        text = self._tok.decode(
            out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        return _parse_json_object(text)


class OpenAICompatNamer:
    """Open-model naming via an OpenAI-compatible chat endpoint (ADR-067).

    The default and recommended path: a Llama served locally by Ollama
    (``ollama pull llama3.1`` → ``http://localhost:11434/v1``) — key-free, free, and
    reproducible, keeping the whole pipeline runnable without any paid API. The same
    client also drives any hosted OpenAI-compatible Llama endpoint (Together, Groq,
    Fireworks, vLLM) by pointing ``base_url`` / setting ``MND_NAMING_API_KEY``.

    Uses only ``urllib`` (no SDK dependency). Temperature 0 → greedy/deterministic,
    so the committed name cache stays meaningful. Unreachable endpoint → the first
    call raises and ``generate_names`` aborts to c-TF-IDF labels (no key required).
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "OpenAICompatNamer":
        import os

        nc = (cfg.get("display") or {}).get("naming") or {}
        base_url = os.environ.get("MND_NAMING_BASE_URL", nc.get("base_url", "http://localhost:11434/v1"))
        model = os.environ.get("MND_NAMING_MODEL", nc.get("model", "llama3.1"))
        api_key = os.environ.get("MND_NAMING_API_KEY", nc.get("api_key"))
        return cls(base_url, model, api_key)

    def name_cluster(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import urllib.request

        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},  # honored where supported
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + '\n\nRespond with only a JSON object: {"title": ..., "description": ...}'},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return _parse_json_object(body["choices"][0]["message"]["content"])


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

    import os

    # Default: open Llama via an OpenAI-compatible endpoint (Ollama), key-free and
    # reproducible (ADR-067). "local" = in-process transformers; "anthropic" = paid.
    backend = str(nc.get("backend", "llama")).lower()
    # The cache key includes the effective model id, so a backend/model switch never
    # serves another backend's titles from cache.
    if backend == "llama":
        model = str(os.environ.get("MND_NAMING_MODEL", nc.get("model", "llama3.1")))
    elif backend == "local":
        model = str(nc.get("local_model", "Qwen/Qwen2.5-7B-Instruct"))
    else:
        model = str(nc.get("model", "claude-haiku-4-5"))
    prompt_version = int(nc.get("prompt_version", 1))
    title_words = int(nc.get("max_title_words", 7))
    cache_dir = Path(nc.get("cache_dir", "data/naming_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)

    out: dict[int, NarrativeName] = {}
    misses: list[tuple[NamingInput, Path]] = []
    for inp in inputs:
        sig = _signature(inp, model, prompt_version, title_words)
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
            builder = {
                "llama": OpenAICompatNamer,
                "local": LocalHFNamer,
                "anthropic": AnthropicNamer,
            }.get(backend, OpenAICompatNamer)
            try:
                client = builder.from_config(cfg)
            except Exception as exc:
                log.warning(
                    "Narrative naming skipped — no %s client (%s); %d clusters keep "
                    "c-TF-IDF labels (%d served from cache)",
                    backend, exc, len(misses), n_cached,
                )
                return out
        produced_any = False
        for inp, path in misses:
            try:
                d = client.name_cluster(_SYSTEM, _build_user(inp, title_words), _SCHEMA)
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
