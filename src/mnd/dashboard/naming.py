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
    # v6 context (ADR-056): dated article titles across the lifespan — the
    # strongest naming signal the corpus carries (headlines written by humans).
    # Each entry is "YYYY-MM-DD — title". central/earliest enter the cache
    # signature; newest do NOT (they roll forward every weekly merge, and a few
    # new arrivals must not regenerate a settled title — same rationale as
    # excluding the date span, ADR-070).
    central_titles: list[str] = field(default_factory=list)
    earliest_titles: list[str] = field(default_factory=list)
    newest_titles: list[str] = field(default_factory=list)
    n_articles: int | None = None    # excluded from the signature (grows weekly)
    peak_date: str | None = None     # excluded from the signature (can shift)


@dataclass(frozen=True)
class NarrativeName:
    title: str
    description: str


def naming_input_from_card(
    cluster_id: int, terms: list[str], card: dict[str, Any]
) -> NamingInput:
    """Build the v6 NamingInput from a story-card dict (ADR-061/080).

    The single constructor both naming paths share — the ``analyze`` bake (from
    ``StoryCard.to_dict()``) and the post-bake ``name`` job (from the baked
    ``card`` JSON) — so their cache signatures are identical and every name is
    generated exactly once wherever the namer runs.
    """
    def _dated(panel: Any) -> list[str]:
        out = []
        for a in panel or []:
            title = str(a.get("title") or "").strip()
            if not title:
                continue
            day = str(a.get("published_at") or "")[:10]
            out.append(f"{day} — {title}" if day else title)
        return out

    panels = card.get("central_articles") or card.get("representative_articles") or []
    dr = card.get("date_range")
    return NamingInput(
        cluster_id=int(cluster_id),
        terms=[str(t) for t in terms],
        excerpts=[a["excerpt"] for a in panels if a.get("excerpt")],
        date_range=tuple(dr) if dr else None,
        sources=[s for s, _ in (card.get("source_mix") or [])[:4]],
        central_titles=_dated(panels),
        earliest_titles=_dated(card.get("earliest_articles")),
        newest_titles=_dated(card.get("newest_articles")),
        n_articles=int(card.get("n_articles") or 0) or None,
        peak_date=card.get("peak_date"),
    )


# System prompt is part of the cache key (via prompt_version) — changing it
# without bumping display.naming.prompt_version would silently reuse stale titles.
_SYSTEM = (
    "You are a news editor naming tracked stories for a public dashboard of "
    "macro-financial discourse. Each story is a cluster of related institutional "
    "and academic writing (Fed, IMF, BIS, CBO, think tanks, NBER) followed over "
    "years. You receive a JSON object with the cluster's machine-extracted "
    "keywords, its top sources, its active date span and peak date, dated titles "
    "of articles from across its life (earliest, most central, most recent), and "
    "excerpts from its most central documents.\n\n"
    "Write two things:\n"
    "- title: a wire-desk story slug — a specific noun phrase that tells a reader "
    "what the story IS: the actor plus the action, dispute, or subject. 'US "
    "sanctions against Hezbollah', 'ECB press conferences on the inflation "
    "outlook', 'Regional bank deposit runs', 'CBO scoring of pandemic relief "
    "bills'. NOT a vague category box: 'Work-home arrangements', 'Iraqi political "
    "landscape', 'Economic uncertainty' tell the reader nothing — every draft "
    "must answer 'who is doing what, or what is being debated?'. Around 4 to 8 "
    "words.\n"
    "- description: one paragraph of 4 to 6 plain, concrete sentences for an "
    "interested non-expert: what the writing covers, who the main actors are, "
    "how the story ran over its span (what set it off where the material shows "
    "it, what it centered on at its height, and whether it faded or continues), "
    "and why it mattered. Write about the subject itself, never about the "
    "collection: open with the subject ('Interviews with X tracked...', 'The "
    "shale boom transformed...'), never with 'This collection', 'This writing "
    "cluster', 'This material', or 'Writing from X tracks'.\n\n"
    "Grounding:\n"
    "- The dated article titles are your strongest evidence; the keywords are "
    "noisy machine output. Weigh titles and excerpts over keywords.\n"
    "- You may use your knowledge of economic history to recognize the story the "
    "material tracks — if dated titles about bond-market selloffs cluster in mid-"
    "2013, it is the taper tantrum and you should say so. But never force an "
    "event the dates or titles contradict, and never import facts, numbers, or "
    "outcomes the material neither contains nor clearly points to.\n"
    "- A cluster can drift: early and late articles may sit off the core story. "
    "Name the story that carries the bulk of the material (the central titles "
    "and excerpts), not a stray outlier.\n"
    "- The active span is the coverage window, not any one person's tenure. "
    "Never attribute the whole span to a single actor: if the dated titles show "
    "an officeholder's era ending and successors continuing the story, say so "
    "rather than stretching one name across the full range.\n"
    "- If the material does not say why something happened, leave the why out — "
    "no 'likely', 'possibly', 'may have' padding, and never write that something "
    "is unspecified or not stated.\n"
    "- When only keywords are supplied, stay modest: connect them into a natural, "
    "grammatical phrase using whatever country, institution, or actor they "
    "identify; do not invent relationships between them.\n"
    "- If the material is not about economics or finance, name it plainly for "
    "what it is rather than forcing an economic framing.\n\n"
    "Form:\n"
    "- Sentence case for the title, always: capitalize the first word, proper "
    "nouns, and acronyms — nothing else. 'Regional bank deposit runs', never "
    "'Regional Bank Deposit Runs'. If every word of your draft starts with a "
    "capital, rewrite it before answering.\n"
    "- No commas, colons, semicolons, quotation marks, or trailing period in the "
    "title, and no date ranges in it (the span is shown separately). A year may "
    "appear only when it names the event itself ('2013 taper tantrum').\n"
    "- Standard English capitalization for proper nouns everywhere: countries, "
    "people, organizations, currencies, named laws (Dodd-Frank, CARES Act), "
    "'EO 13224', 'William C. Dudley'.\n"
    "- Keywords can be malformed — run together ('officetoresidential') or "
    "oddly split. Write normal English with correct spacing and hyphens "
    "('office-to-residential conversions'). Never copy URL fragments, file "
    "paths, or document IDs into the title.\n"
    "- Neutral and factual: no hype, no editorializing, no forecasting.\n"
    "- Write about the subject directly. Never refer to 'this narrative', 'this "
    "cluster', 'these articles', 'the material', or 'the dashboard'; never open "
    "with 'Explores' or 'In the world of'. Vary how descriptions open.\n"
    "- Return strictly the requested JSON; no markdown.\n\n"
    "Title contrast — vague box vs. story:\n"
    "- 'Work home arrangements' -> 'Remote work and the future of office demand'\n"
    "- 'Iraqi political landscape' -> 'Iraq's reconstruction and oil politics'\n"
    "- 'Monetary policy communication' -> 'Forward guidance at the zero lower bound'\n"
    "- 'Governor press conferences' -> 'Bank of England guidance after the Brexit vote'\n\n"
    "Example (full material):\n"
    '{"title": "Federal Reserve rate normalization after 2015", "description": '
    '"After seven years of near-zero rates, the Federal Reserve began raising the '
    "federal funds rate in December 2015 and debated the pace of tightening for "
    "the rest of the decade. FOMC statements and speeches weighed a firming labor "
    "market against inflation that kept undershooting the 2% target. Regional Fed "
    "presidents argued publicly over how much slack remained, and each meeting's "
    "language was parsed for the timing of the next hike. The path of hikes set "
    "borrowing costs across the economy and became the benchmark for when "
    '\\"normal\\" policy had returned. The debate wound down as rates plateaued in '
    '2019."}\n'
    "Example (keywords only — modest is correct):\n"
    '{"title": "Central bank independence debates", "description": '
    '"Recurring arguments over how much political influence central banks should '
    'face, drawn from multiple countries and institutions."}'
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
    # US government agencies and programs
    "va", "sba", "ppe", "arp", "slfrf", "aca", "arra",
    "doj", "dhs", "dod", "hud", "hhs", "cfpb", "fhfa", "fha",
    "irs", "fcc", "epa", "fda", "gao", "omb", "cia", "nsa",
    "eo",          # Executive Order
    # financial instruments / market structure
    "uav", "jgb", "aml", "cft", "agoa",
    "lbo", "clo", "mbs", "abs", "cdo",
    "rbi", "boc", "rba", "bnm",       # central banks (Reserve Bank India, Bank of Canada/Australia/Malaysia)
    "fdi", "spac", "nlp", "agi",
}
# Single-word proper nouns (countries, demonyms, cities, institutions, people)
# that the 7B-class models leave lowercase after copying the c-TF-IDF keywords.
# Capitalized (first letter), not up-cased. Trailing possessive is stripped for
# the lookup, so "china's" matches "china". Kept to items that actually surfaced
# in the corpus titles and are unambiguous in a macro-finance context.
_PROPER = {
    # continents / regions
    "america", "american", "africa", "african", "asia", "asian",
    "europe", "european", "latin", "caribbean", "pacific", "atlantic",
    "nordic", "mediterranean", "eurasia", "balkans", "scandinavia",
    "subsaharan",   # glued form; also handled by FIXUPS for the full phrase
    # countries and demonyms
    "china", "chinese", "japan", "japanese", "india", "indian",
    "korea", "korean", "germany", "german", "france", "french",
    "russia", "russian", "ukraine", "ukrainian", "iran", "iranian",
    "israel", "israeli", "syria", "syrian", "iraq", "iraqi", "turkey",
    "turkish", "greece", "greek", "italy", "italian", "spain", "spanish",
    "portugal", "portuguese", "ireland", "irish", "iceland", "brazil",
    "brazilian", "mexico", "mexican", "canada", "canadian", "argentina",
    "venezuela", "egypt", "egyptian", "libya", "libyan", "cyprus",
    "sudan", "sudanese", "afghanistan", "afghan", "pakistan", "pakistani",
    "indonesia", "indonesian", "vietnam", "vietnamese", "nigeria",
    "nigerian", "kenya", "kenyan", "ghana", "ghanaian", "zambia", "zambian",
    "senegal", "senegalese", "tanzania", "tanzanian", "zimbabwe",
    "ethiopia", "ethiopian", "rwanda", "rwandan", "myanmar", "burmese",
    "colombia", "colombian", "chile", "chilean", "peru", "peruvian",
    "qatar", "qatari", "bahrain", "bahraini", "kuwait", "kuwaiti",
    "jordan", "jordanian", "lebanon", "lebanese", "morocco", "moroccan",
    "algeria", "algerian", "tunisia", "tunisian", "serbia", "serbian",
    "albania", "albanian", "romania", "romanian", "bulgaria", "bulgarian",
    "croatia", "croatian", "ukraine", "ukrainian",
    "australia", "australian", "britain", "british", "swiss", "dutch",
    "belgian", "swedish", "norwegian", "danish", "finnish", "austrian",
    "polish", "hungarian", "czech", "slovak", "philippine", "philippino",
    "malaysia", "malaysian", "thailand", "thai", "bangladesh", "bangladeshi",
    "singapore", "singaporean",
    "taiwan", "taiwanese",
    "ukraine", "ukrainian",   # also above in countries section, idempotent
    "israel", "israeli",      # same
    # cities
    "washington", "beijing", "brussels", "frankfurt", "basel", "davos",
    "london", "tokyo", "paris", "moscow", "tehran", "gaza", "detroit",
    "chicago", "shanghai", "geneva", "vienna", "delhi", "mumbai",
    "istanbul", "riyadh", "kyiv", "taipei", "seoul", "jakarta",
    "manila", "nairobi", "cairo", "abuja", "accra", "kampala",
    # institutions / bodies
    "congress", "senate", "treasury", "fed", "brexit",
    "pentagon", "kremlin", "bundestag", "riksbank",
    # central bankers and finance officials (surnames)
    "draghi", "trichet", "bernanke", "yellen", "powell", "lagarde",
    "greenspan", "volcker", "mnuchin", "goolsbee", "kuroda", "merkel",
    "macron", "trump", "biden", "obama", "putin", "erdogan", "modi",
    "dudley", "poloz", "lew", "geithner", "carney", "subbarao",
    "nabiullina", "sejko", "morsi", "haftar", "netanyahu", "zelensky",
    "scholz", "sunak", "orban", "milei", "lula", "bolsonaro",
    "kashkari", "bullard", "waller", "brainard", "clarida",
    # first names that appear without a surname in titles
    "mario",     # Mario Draghi
    "janet",     # Janet Yellen
    # armed groups / political movements kept for disambiguation
    "lehman", "hezbollah", "hamas", "taliban", "houthi", "daesh",
    # accented forms (bare lowercase from c-TF-IDF)
    "obrador",   # Andrés Manuel López Obrador
    "lópez",     # López Obrador (accented form)
    "draghi",
}
_FIXUPS = {
    # --- institutions and bodies ---
    "federal reserve": "Federal Reserve",
    "federal open market committee": "Federal Open Market Committee",
    "beige book": "Beige Book",
    "jackson hole": "Jackson Hole",
    "wall street": "Wall Street",
    "white house": "White House",
    "u.s.": "U.S.",
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
    "dodd-frank": "Dodd-Frank",
    "affordable care act": "Affordable Care Act",
    "cares act": "CARES Act",
    # --- geographic multi-word phrases ---
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
    "subsaharan africa": "Sub-Saharan Africa",
    "east africa": "East Africa",
    "west africa": "West Africa",
    "central africa": "Central Africa",
    "north africa": "North Africa",
    "southeast asia": "Southeast Asia",
    "south asia": "South Asia",
    "east asia": "East Asia",
    "central asia": "Central Asia",
    "eastern europe": "Eastern Europe",
    "western europe": "Western Europe",
    "euro area": "euro area",
    "east china sea": "East China Sea",
    "south china sea": "South China Sea",
    "persian gulf": "Persian Gulf",
    # --- central banks ---
    "bank of japan": "Bank of Japan",
    "bank of england": "Bank of England",
    "bank of france": "Bank of France",
    "bank of canada": "Bank of Canada",
    "bank of italy": "Bank of Italy",
    "bank of spain": "Bank of Spain",
    "bank of mexico": "Bank of Mexico",
    "bank of korea": "Bank of Korea",
    "bank of albania": "Bank of Albania",
    "reserve bank of india": "Reserve Bank of India",
    "reserve bank of australia": "Reserve Bank of Australia",
    "people's bank of china": "People's Bank of China",
    "south african reserve bank": "South African Reserve Bank",
    "national bank of romania": "National Bank of Romania",
    "norges bank": "Norges Bank",
    "swiss national bank": "Swiss National Bank",
    # --- named people (multi-word; single words handled by _PROPER) ---
    "ben bernanke": "Ben Bernanke",
    "jean-claude trichet": "Jean-Claude Trichet",
    "jean-claude": "Jean-Claude",
    "william c. dudley": "William C. Dudley",
    "william c dudley": "William C. Dudley",
    "william dudley": "William Dudley",
    "jack lew": "Jack Lew",
    "steven mnuchin": "Steven Mnuchin",
    "steve mnuchin": "Steve Mnuchin",
    "janet yellen": "Janet Yellen",
    "jerome powell": "Jerome Powell",
    "neel kashkari": "Neel Kashkari",
    "duvvuri subbarao": "Duvvuri Subbarao",
    "elvira nabiullina": "Elvira Nabiullina",
    "stephen poloz": "Stephen Poloz",
    "gent sejko": "Gent Sejko",
    "philip lowe": "Philip Lowe",
    "andrés manuel lópez obrador": "Andrés Manuel López Obrador",
    "lópez obrador": "López Obrador",
    "lopez obrador": "López Obrador",
    # --- possessive / plural slips from keyword copy ---
    "chinas": "China's",
    "russias": "Russia's",
    "americas": "Americas",
    "hezbollahs": "Hezbollah's",
    "hamass": "Hamas's",
    "talibans": "Taliban's",
    # --- glued / run-together forms ---
    "crossborder": "cross-border",
    "crossstrait": "cross-strait",
    "subsaharan": "Sub-Saharan",
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
    "usuk": "US-UK",
    "useu": "US-EU",
    # garbled accented form from keyword copy (missing ó)
    "lpez": "López",
}

# Strip a trailing possessive so proper-noun lookup matches ("china's" -> "china").
_POSSESSIVE = re.compile(r"['’]s$")

# Collection meta-language the prompt forbids at the start of a description
# ("This collection of interviews tracks…"). Detectable deterministically, so a
# violation triggers one corrective retry (ADR-080) instead of shipping.
_META_OPEN_RE = re.compile(
    r"^\s*(?:this|these)\s+(?:collection|cluster|writing|writings|material|"
    r"articles|documents|records|group|set|body)\b"
    r"|^\s*writing\s+from\b",
    re.IGNORECASE,
)

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
# is what remains.  6-digit bare numbers (CBO catalog IDs like "086690") are
# stripped; 5-digit numbers are NOT, because Executive Order numbers (13224,
# 14024 ...) are 5-digit and meaningful.
_ARTIFACT_RE = re.compile(
    r"\b(?:kdocs\d+\w*|sdeneendocs\d+\w*|\d{6})\b",
    re.IGNORECASE,
)

# Unicode decimal entity artifacts: models occasionally emit curly-quote
# characters (U+2018/2019) that survive JSON serialization as their decimal
# code points (8216/8217).  e.g. "Act8217s" → "Act's", "it8217s" → "it's".
_UNICODE_APOS_RE = re.compile(r"(\w)8217s\b")
_UNICODE_QUOT_RE = re.compile(r"\b8216(\w)")

# URL / protocol artifacts: LLMs occasionally copy a keyword that looks like
# a URL scheme ("https", "http", "www") into the title verbatim.
_URL_PREFIX_RE = re.compile(r"^https?:?\s*", re.IGNORECASE)


def _polish_title(title: str) -> str:
    """Deterministic casing repair: first letter, acronyms, proper nouns.

    Order: artifact/encoding fixes first, then multi-word fixups (so "united
    states" wins before per-word handling), then per-word acronym up-casing and
    proper-noun capitalization, then the leading capital. Up-casing/capitalizing
    a fixed list is safe in a way the reverse (de-Title-Casing, which needs to
    know which words are proper) is not; the list only grows, and because polish
    also runs on cache read the growth lands on the next bake with no
    regeneration (ADR-056).
    """
    t = title.strip()
    # Fix unicode decimal entities from LLM curly-quote output
    # ("Act8217s" → "Act's", i.e. U+2019 RIGHT SINGLE QUOTATION MARK).
    t = _UNICODE_APOS_RE.sub(r"\1's", t)
    t = _UNICODE_QUOT_RE.sub(r"'\1", t)
    # Strip leading URL/protocol artifacts ("Https reciprocal..." → "Reciprocal...")
    t = _URL_PREFIX_RE.sub("", t).strip()
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


_KEYWORD_ARTIFACT_RE = re.compile(
    r"^(?:https?|www|ftp)$"          # bare URL protocols
    r"|^https?://"                    # full URL prefix
    r"|\bkdocs\d+\w*"                 # CBO filename fragments
    r"|\bsdeneendocs\d+\w*",
    re.IGNORECASE,
)


def _build_user(inp: NamingInput, title_words: int) -> str:
    """Render one cluster's representation into the user message (v6: JSON in)."""
    clean_terms = [t for t in inp.terms if not _KEYWORD_ARTIFACT_RE.search(t)]
    payload: dict[str, Any] = {"keywords": clean_terms[:15]}
    if inp.sources:
        payload["sources"] = inp.sources[:4]
    if inp.n_articles:
        payload["n_articles"] = int(inp.n_articles)
    if inp.date_range:
        payload["active"] = {"from": inp.date_range[0], "to": inp.date_range[1]}
        if inp.peak_date:
            payload["active"]["peak"] = inp.peak_date
    titles: dict[str, list[str]] = {}
    if inp.earliest_titles:
        titles["earliest"] = inp.earliest_titles[:4]
    if inp.central_titles:
        titles["most_central"] = inp.central_titles[:4]
    if inp.newest_titles:
        titles["most_recent"] = inp.newest_titles[:4]
    if titles:
        payload["article_titles"] = titles
    if inp.excerpts:
        payload["central_excerpts"] = [ex.strip()[:700] for ex in inp.excerpts[:3]]
    lines = [json.dumps(payload, ensure_ascii=False, indent=1)]
    if not inp.excerpts and not titles:
        # directory/terms-only path (ADR-073): no excerpts or titles exist for
        # sub-floor clusters — say so explicitly so the model stays modest
        # instead of inferring a specific event from keyword resemblance alone.
        lines.append(
            "Only keywords are available for this cluster; ground the title in "
            "them alone and stay general."
        )
    lines.append(
        "\nReturn JSON with two keys: title (a specific story slug — roughly "
        f"{title_words} words, sentence case, never a full sentence, no trailing "
        "period) and description (one paragraph, 4 to 6 plain, concrete sentences)."
    )
    return "\n".join(lines)


def _signature(
    inp: NamingInput, model: str, prompt_version: int, max_title_words: int
) -> str:
    """Content hash of everything that determines the generated title.

    Keyed on the substance of the representation (terms, excerpts, sources,
    central/earliest article titles) plus the model, prompt version, and
    title-length knob. The date span, peak date, article count, and *newest*
    titles are deliberately excluded (ADR-070): a continuing narrative extends
    all of these every weekly merge, and that alone must not regenerate its
    title — names change only when the substance does.
    """
    payload = json.dumps(
        {
            "t": inp.terms,
            "e": inp.excerpts,
            "s": list(inp.sources),
            "ct": list(inp.central_titles),
            "et": list(inp.earliest_titles),
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
    a code fence, or append garbage after the closing brace (7B-class models
    occasionally emit trailing tool-call fragments). ``raw_decode`` from the
    first ``{`` parses the first *complete* object and ignores anything after
    it, where a first-``{``-to-last-``}`` slice chokes on the trailing junk.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in model output: {text[:120]!r}")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError(f"model output is not a JSON object: {text[:120]!r}")
    return obj


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
    (``ollama pull gemma3:12b`` → ``http://localhost:11434/v1``), key-free, free, and
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
        model = os.environ.get("MND_NAMING_MODEL", nc.get("model", "gemma3:12b"))
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
        model = str(os.environ.get("MND_NAMING_MODEL", nc.get("model", "gemma3:12b")))
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
                user = _build_user(inp, title_words)
                d = client.name_cluster(_SYSTEM, user, _SCHEMA)
                # Conditional second pass (ADR-080): when the description opens
                # with collection meta-language the prompt forbids — a violation
                # a regex can detect — re-ask once with corrective feedback.
                # Cheaper and more deterministic than a blanket rewrite pass;
                # typography is already covered by _polish_title.
                if _META_OPEN_RE.match(str(d.get("description", ""))):
                    retry_user = (
                        user
                        + "\n\nYour previous description began with collection "
                        "meta-language ('" + str(d["description"])[:60] + "...'). "
                        "Rewrite it to open with the subject itself — the actor "
                        "or event — never with 'This collection', 'This cluster', "
                        "'The material', or 'Writing from'."
                    )
                    try:
                        d2 = client.name_cluster(_SYSTEM, retry_user, _SCHEMA)
                        if not _META_OPEN_RE.match(str(d2.get("description", ""))):
                            d = d2
                    except Exception:
                        pass  # keep the first result; the retry is best-effort
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
