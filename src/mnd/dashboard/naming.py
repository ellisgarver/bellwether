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
import re
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
    "narratives rise and fade. You are given a cluster's defining keywords, and "
    "usually short excerpts from its most central documents plus its active date "
    "span.\n\n"
    "Write two things:\n"
    "- title: a short, specific noun phrase naming what the writing is about — a "
    "headline, not a sentence, and not a bare keyword. Name the period or event "
    "when the excerpts make it clear.\n"
    "- description: 2 to 4 plain, concrete sentences on what the writing covers and, "
    "where the material itself shows it, why it mattered — written for an interested "
    "non-expert.\n\n"
    "Rules:\n"
    "- Sentence case for the title, always: capitalize the first word, proper "
    "nouns, and acronyms — nothing else. Write 'Regional bank deposit runs', "
    "never 'Regional Bank Deposit Runs'. This holds for every subject, economic "
    "or not. If every word of your draft title starts with a capital letter, "
    "rewrite it in sentence case before answering.\n"
    "- Ground everything in the supplied material. Do not add events, places, dates, "
    "numbers, causes, or outcomes that are not present in it. If the keywords "
    "resemble a well-known event, name that event only when the excerpts confirm "
    "it; otherwise stay general.\n"
    "- If the material does not say why something happened, leave the why out — "
    "no 'likely', 'possibly', or 'may have been influenced by' padding. Never "
    "write that something is unspecified, implied, or not stated; just leave it "
    "out.\n"
    "- When no excerpts are supplied, title from the keywords alone, and prefer a "
    "modest descriptive phrase over guessing a specific event or storyline. Do "
    "not invent relationships or actions connecting the people and institutions "
    "the keywords name. Connect the keywords into a natural phrase; never output "
    "a bare list of keywords as the title.\n"
    "- Keywords are machine-extracted and can be malformed — run together "
    "('officetoresidential') or oddly split. Write the title in normal English "
    "with correct spacing and hyphens ('office-to-residential conversions').\n"
    "- If the material is not about economics or finance, name it plainly for what it "
    "actually is rather than forcing an economic framing.\n"
    "- Neutral and factual: no hype, no editorializing, no forecasting, no advice.\n"
    "- Write about the subject directly, as if the reader is looking at the "
    "documents themselves. Never refer to 'this narrative', 'this cluster', 'this "
    "topic', 'these articles', 'the writing', 'the material', 'the excerpts', "
    "'the keywords', or 'the dashboard', and never open with 'Explores' or 'In "
    "the world of'. Vary how you open across descriptions.\n"
    "- No quotation marks around the title, no trailing period on it, no markdown "
    "anywhere.\n"
    "Return strictly the requested JSON.\n\n"
    "Example (with excerpts):\n"
    '{"title": "Municipal bond market stress, 2010\\u20132011", "description": '
    '"State and local governments faced rising borrowing costs as investors '
    "questioned the safety of municipal debt. Analysts weighed default risk "
    "against the market's long record of low losses, and the debate shaped how "
    'pension shortfalls were reported."}\n'
    "Example (keywords only):\n"
    '{"title": "Crop insurance and farm subsidy programs", "description": '
    '"Federal support for farmers through crop insurance and direct subsidies, '
    'and the recurring budget debates over the cost of both."}\n'
    "Example (keywords only, not economics — sentence case still applies):\n"
    '{"title": "Conference planning and event logistics", "description": '
    '"Professional conferences are organized around registration, hotel '
    'arrangements, agendas, and keynote sessions."}\n'
    "Example (keywords only, mostly names — stay modest, connect nothing):\n"
    '{"title": "European leaders and transatlantic relations", "description": '
    '"European heads of government manage their countries\' relations with the '
    'United States, and recurring surveys track how those relationships '
    'shift."}'
)

# Deterministic title cleanup applied after generation, before caching. The
# 7B-class open models copy the lowercase c-TF-IDF keywords into titles
# ("detroit", "Gdp cpi"), and up-casing a fixed acronym list plus the first
# letter is safe in a way the reverse (de-Title-Casing, which needs to know
# which words are proper nouns) is not.
_ACRONYMS = {
    "gdp", "cpi", "pce", "ppi", "fomc", "imf", "bis", "cbo", "cea", "ofr",
    "nber", "svb", "vix", "qe", "qt", "ecb", "boe", "boj", "pboc", "snb",
    "fdic", "sec", "occ", "fsoc", "tarp", "btfp", "wto", "nato", "opec",
    "ai", "uk", "eu", "un", "us", "jel", "zlb", "nairu", "cds", "etf", "ipo",
    "reit", "tips", "sofr", "libor",
    # added 2026-07-12 from the full-bake title scan
    "ieepa", "covid", "esg", "cbdc", "oecd", "asean", "brics", "nafta",
    "usmca", "gdpr", "llm", "llms", "gse", "gses", "sme", "smes", "ppp",
    "g7", "g20", "oled", "fsb", "bri", "wmd",
    # added 2026-07-13 from the full-bake title scan
    "usaid", "uscis",
    # legislative bill types (HR = House Resolution/Bill, S = Senate Bill)
    "hr", "hres", "hjres", "sjres",
}
# Single-word proper nouns (countries, demonyms, cities, institutions, people)
# that the 7B-class models leave lowercase after copying the c-TF-IDF keywords.
# Capitalized (first letter), not up-cased. Trailing possessive is stripped for
# the lookup, so "china's" matches "china". Kept to items that actually surfaced
# in the corpus titles and are unambiguous in a macro-finance context.
_PROPER = {
    "america", "american", "africa", "african", "asia", "asian",
    "europe", "european", "latin", "caribbean", "pacific", "atlantic",
    "nordic", "mediterranean", "eurasia", "balkans", "scandinavia",
    "china", "chinese", "japan", "japanese", "india", "indian",
    "korea", "korean", "germany", "german", "france", "french",
    "russia", "russian", "ukraine", "ukrainian", "iran", "iranian",
    "israel", "israeli", "syria", "syrian", "iraq", "iraqi", "turkey",
    "turkish", "greece", "greek", "italy", "italian", "spain", "spanish",
    "portugal", "portuguese", "ireland", "irish", "iceland", "brazil",
    "brazilian", "mexico", "mexican", "canada", "canadian", "argentina",
    "venezuela", "egypt", "libya", "cyprus", "sudan", "afghanistan",
    "afghan", "pakistan", "indonesia", "vietnam", "nigeria", "kenya",
    "australia", "australian", "britain", "british", "swiss", "dutch",
    "belgian", "swedish", "norwegian", "danish", "finnish", "austrian",
    "polish", "hungarian", "czech", "slovak", "romanian", "bulgarian",
    "washington", "beijing", "brussels", "frankfurt", "basel", "davos",
    "london", "tokyo", "paris", "moscow", "tehran", "gaza", "detroit",
    "chicago", "shanghai", "geneva", "vienna",
    "congress", "senate", "treasury", "fed", "brexit",
    "draghi", "trichet", "bernanke", "yellen", "powell", "lagarde",
    "greenspan", "volcker", "mnuchin", "goolsbee", "kuroda", "merkel",
    "macron", "trump", "biden", "obama", "putin", "erdogan", "modi",
    "lehman", "hezbollah", "hamas", "taliban",
    # added 2026-07-13: surnames and first names the 7B models leave lowercase
    "obrador",   # Andrés Manuel López Obrador
    "subbarao",  # Duvvuri Subbarao (RBI Governor)
    "geithner",  # Timothy Geithner
    "carney",    # Mark Carney (BoE / BoC)
    "mario",     # Mario Draghi
    "lópez",     # López Obrador (accented form; "lopez" without accent gets leading-cap)
}
_FIXUPS = {
    "federal reserve": "Federal Reserve",
    "federal open market committee": "Federal Open Market Committee",
    "beige book": "Beige Book",
    "jackson hole": "Jackson Hole",
    "wall street": "Wall Street",
    "white house": "White House",
    "u.s.": "U.S.",
    # multi-word places and institutions (added 2026-07-12)
    "united states": "United States",
    "united kingdom": "United Kingdom",
    "united nations": "United Nations",
    "european union": "European Union",
    "european central bank": "European Central Bank",
    "world bank": "World Bank",
    "world trade organization": "World Trade Organization",
    "international monetary fund": "International Monetary Fund",
    "supreme court": "Supreme Court",
    "silicon valley": "Silicon Valley",
    "middle east": "Middle East",
    "hong kong": "Hong Kong",
    "new york": "New York",
    "north korea": "North Korea",
    "south korea": "South Korea",
    "south sudan": "South Sudan",
    "saudi arabia": "Saudi Arabia",
    "puerto rico": "Puerto Rico",
    "latin america": "Latin America",
    "sub-saharan africa": "Sub-Saharan Africa",
    "euro area": "euro area",
    "bank of japan": "Bank of Japan",
    "bank of england": "Bank of England",
    "bank of france": "Bank of France",
    "bank of canada": "Bank of Canada",
    "bank of italy": "Bank of Italy",
    "bank of spain": "Bank of Spain",
    "bank of mexico": "Bank of Mexico",
    "bank of korea": "Bank of Korea",
    "reserve bank of india": "Reserve Bank of India",
    "people's bank of china": "People's Bank of China",
    "south african reserve bank": "South African Reserve Bank",
    "east china sea": "East China Sea",
    "south china sea": "South China Sea",
    # possessive spelling slips the models introduce from the keyword copy
    "chinas": "China's",
    "americas": "Americas",
    # multi-word paired names where the first name is a common word
    "ben bernanke": "Ben Bernanke",
    "jean-claude trichet": "Jean-Claude Trichet",
    "jean-claude": "Jean-Claude",
    # merged US–country/region names the 7B models produce from glued c-TF-IDF keywords
    # (us-china with a hyphen already resolves via _PROPER; these are the no-hyphen forms)
    "uschina": "US-China",
    "usindia": "US-India",
    "usgermany": "US-Germany",
    "usjapan": "US-Japan",
    "usjapanese": "US-Japanese",
    "usbrazil": "US-Brazil",
    "usafrica": "US-Africa",
    "usmexico": "US-Mexico",
    "ussaudi": "US-Saudi",
    "usasean": "US-ASEAN",
    "usrok": "US-ROK",
    # garbled accented form from keyword copy (missing ó)
    "lpez": "López",
}

# Strip a trailing possessive so proper-noun lookup matches ("china's" -> "china").
_POSSESSIVE = re.compile(r"['’]s$")

# Trailing date stamp the models copy out of the span ("…, 2010-2026", "… 2018",
# "…, 2022-23", "…2011-present"). The date span is shown separately on every card,
# so it is redundant in the title. Only a *trailing* date is stripped, never a
# leading/among one that carries meaning ("2013 taper tantrum", "COVID-19").
_TRAILING_DATE = re.compile(
    r"[\s,;:()\[\]]*"                                  # separators before the date
    r"(?:19|20)\d{2}"                                  # a 4-digit year
    r"(?:"
    r"(?:19|20)\d{2}"                                  # a glued second year ("19782012")
    r"|\s*(?:[-–—/]|to|through)\s*"                    # or a separated range
    r"(?:(?:19|20)?\d{2}|present|now|onwards?|date|x|\?)"
    r")?"
    r"\s*$",
    re.IGNORECASE,
)


def _cap_proper(word: str) -> str:
    """Capitalize the first letter of a proper-noun token, leaving the rest."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1:]
    return word


def _polish_word(w: str) -> str:
    """Acronym up-cast or proper-noun capitalization for one whitespace token.

    Applied to each hyphen-separated subpart too, so the models' glued country
    pairs recover ("us-india" -> "US-India"); ordinary hyphenates are untouched
    because neither part is in the lists ("cross-strait" stays lowercase)."""
    core = w.lower().strip(",.:;()'’")
    if core in _ACRONYMS:
        return w.upper()
    # Look up the proper-noun base: drop a possessive ("china's" -> "china"),
    # then, failing that, a bare trailing "s" ("trichets"/"germans"). Only the
    # capitalization is applied to the original token — no apostrophe is
    # fabricated, since "koreas" could be plural rather than possessive.
    base = _POSSESSIVE.sub("", core)
    if base not in _PROPER and base.endswith("s"):
        base = base[:-1]
    if base in _PROPER:
        return _cap_proper(w)
    if "-" in core and "-" in w:
        parts = w.split("-")
        if len(parts) > 1:
            return "-".join(_polish_word(p) for p in parts)
    return w


# CBO distributes PDFs whose filenames / catalog tokens leak into extracted
# text and surface as top c-TF-IDF terms (e.g. "kdocs37448txt", "086690").
# Strip them from titles before any other processing so the LLM's real content
# is what remains.  The patterns are narrow enough to be safe in a macro-finance
# corpus: no economics paper title legitimately contains "kdocs\d+txt".
_ARTIFACT_RE = re.compile(
    r"\b(?:kdocs\d+\w*|sdeneendocs\d+\w*|\d{5,6})\b",
    re.IGNORECASE,
)


def _polish_title(title: str) -> str:
    """Deterministic casing repair: first letter, acronyms, proper nouns.

    Order: multi-word fixups first (so "united states" wins before per-word
    handling), then per-word acronym up-casing and proper-noun capitalization,
    then the leading capital. Up-casing/capitalizing a fixed list is safe in a
    way the reverse (de-Title-Casing, which needs to know which words are proper)
    is not; the list only grows, and because polish also runs on cache read the
    growth lands on the next bake with no regeneration (ADR-056).
    """
    t = title.strip()
    # Strip CBO artifact tokens (filename fragments like kdocs37448txt) and
    # leading catalog numbers (like 6601, 086690) that are not years.
    t = _ARTIFACT_RE.sub("", t)
    t = re.sub(r"^(?!(?:19|20)\d{2}\b)\d{3,6}\s+", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # Drop a redundant trailing date span, but never the whole title if a date is
    # somehow all it is.
    stripped = _TRAILING_DATE.sub("", t).rstrip(" ,;:-–—")
    if stripped:
        t = stripped
    for k, v in _FIXUPS.items():
        t = re.sub(rf"\b{re.escape(k)}\b", v, t, flags=re.IGNORECASE)
    t = " ".join(_polish_word(w) for w in t.split(" "))
    return (t[0].upper() + t[1:]) if t else t

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
    if inp.excerpts:
        lines.append("Central excerpts:")
        for i, ex in enumerate(inp.excerpts[:3], 1):
            lines.append(f"{i}. {ex.strip()[:500]}")
    else:
        # directory/terms-only path (ADR-073): no excerpts exist for sub-floor
        # clusters — say so explicitly so the model stays modest instead of
        # inferring a specific event from keyword resemblance alone.
        lines.append(
            "No excerpts are available for this cluster; ground the title in the "
            "keywords alone and stay general."
        )
    lines.append(
        "\nReturn JSON with two keys: title (a short, specific phrase — roughly "
        f"{title_words} words, sentence case, never a full sentence, no trailing "
        "period) and description (2 to 4 plain, concrete sentences)."
    )
    return "\n".join(lines)


def _signature(
    inp: NamingInput, model: str, prompt_version: int, max_title_words: int
) -> str:
    """Content hash of everything that determines the generated title.

    Keyed on the substance of the representation (terms, excerpts, sources) plus
    the model, prompt version, and title-length knob. The date span is
    deliberately excluded (ADR-070): a continuing narrative extends its span
    every weekly merge, and that alone must not regenerate its title — names
    change only when the substance does.
    """
    payload = json.dumps(
        {
            "t": inp.terms,
            "e": inp.excerpts,
            "s": list(inp.sources),
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

    The default and recommended path: an open model served locally by Ollama
    (``ollama pull qwen2.5:7b`` → ``http://localhost:11434/v1``), key-free, free, and
    reproducible, keeping the whole pipeline runnable without any paid API. The same
    client drives any hosted OpenAI-compatible endpoint (Together, Groq, Fireworks,
    vLLM) by pointing ``base_url`` / setting ``MND_NAMING_API_KEY``.

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
        model = os.environ.get("MND_NAMING_MODEL", nc.get("model", "qwen2.5:7b"))
        api_key = os.environ.get("MND_NAMING_API_KEY", nc.get("api_key"))
        return cls(base_url, model, api_key)

    def name_cluster(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import urllib.request

        payload = {
            "model": self._model,
            "temperature": 0,
            "seed": 42,  # belt-and-braces with temperature 0; ignored where unsupported
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

    # Default: an open model via an OpenAI-compatible endpoint (Ollama), key-free and
    # reproducible (ADR-067). "local" = in-process transformers; "anthropic" = paid.
    backend = str(nc.get("backend", "llama")).lower()
    # The cache key includes the effective model id, so a backend/model switch never
    # serves another backend's titles from cache.
    if backend == "llama":
        model = str(os.environ.get("MND_NAMING_MODEL", nc.get("model", "qwen2.5:7b")))
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
                # polish on read as well: idempotent, and it lets _FIXUPS /
                # _ACRONYMS grow without invalidating the cache — casing-list
                # changes land on the next bake instead of a full regeneration.
                out[inp.cluster_id] = NarrativeName(
                    _polish_title(str(d["title"])), d["description"]
                )
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
                name = NarrativeName(
                    _polish_title(str(d["title"])), str(d["description"]).strip()
                )
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
