"""Dashboard artifact contract (Phase 5).

This module defines the *seam* between the analysis pipeline and the Streamlit
front end. The pipeline is heavy (parquet of every chunk, a fitted BERTopic
model, embedding matrices, PyMC traces); the website should not touch any of it.
Instead an artifact-builder bakes everything the screen needs into small, plain
JSON, and the front end only ever reads that JSON — it never imports
pymc/bertopic/torch.

Two file kinds live under ``paths.dashboard_artifacts``:

``index.json`` — the lightweight catalogue the gallery / 2-D map / emerging-feed
views iterate over. One ``IndexEntry`` per non-noise narrative plus run-level
metadata (seed, stage threshold, generation time).

``narrative_<cluster_id>.json`` — the full ``NarrativeArtifact`` for one
narrative: its story card, daily volume series, the four dynamics fits (each with
a *reconstructed display curve* so the UI plots curve-vs-observed without
interpreting parameters), model-free shape facts, the stage readout, JEL scope,
and the optional Media-Cloud and markets overlays.

Design rules baked into the contract:

* **Curves, not parameters.** Each fit carries a ``curve`` array already
  evaluated on the volume's time grid. ``params`` is kept too, but only as an
  opaque, model-specific record — the front end is not asked to evaluate ODEs.
* **No best-of-N selection.** All four lenses are emitted (ADR-039) — the front
  end shows one at a time as selectable/tabbed views, never a single "winner".
  ``staging_model`` only names which fit the lifecycle stage keys off.
* **Overlays are display/validation only** (ADR-041/042), surfaced as opt-in
  toggles in the UI. They carry their own "timing not cause" / pre-2017 captions
  so they can never render uncaptioned.
* **Nullable by design.** ``jel``, ``similar``, ``mediacloud``, ``markets`` and
  ``umap_xy`` are ``None`` when unavailable; the builder degrades gracefully rather
  than omitting keys, so the front end can rely on the shape.

Bump ``SCHEMA_VERSION`` on any breaking change; the front end should refuse a
mismatched major version rather than mis-render.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "1"

Stage = Literal["growth", "decay", "dormant"]


# ---------------------------------------------------------------------------
# Shared sub-structures
# ---------------------------------------------------------------------------


@dataclass
class SeriesArtifact:
    """A time series as parallel arrays — JSON-friendly, plot-ready."""

    dates: list[str]            # ISO YYYY-MM-DD, ascending
    values: list[float]
    freq: str = "D"             # pandas offset alias: "D" daily, "W" weekly


@dataclass
class FitArtifact:
    """One dynamics lens fitted to the narrative's volume curve (ADR-039)."""

    model: str                                  # "logistic" | "sir" | "bass"
    converged: bool
    aicc: float | None = None
    r0_mean: float | None = None                # None for Bass (no R0)
    r0_ci: tuple[float, float] | None = None
    peak_time_mean: float | None = None
    peak_time_ci: tuple[float, float] | None = None
    params: dict[str, Any] = field(default_factory=dict)   # model-specific, opaque
    curve: list[float] | None = None            # evaluated on the volume time grid
    failure_reason: str | None = None


@dataclass
class JELArtifact:
    """Post-cluster JEL scope assignment (ADR-020)."""

    code: str
    in_scope: bool
    similarity: float
    runner_up: str
    runner_up_gap: float


@dataclass
class SimilarNarratives:
    """Top-k related narratives by the three ADR-019 §H measures (narrative page).

    Each list is neighbor ``cluster_id``s in descending similarity. Distinct from
    the map's ``IndexEntry.similar_edges`` (semantic-only, weighted): this is the
    per-narrative "related narratives" reading panel showing all three measures.
    The front end resolves ids → labels via ``index.json``.
    """

    semantic: list[int] = field(default_factory=list)
    lexical: list[int] = field(default_factory=list)
    morphological: list[int] = field(default_factory=list)


@dataclass
class MediaCloudArtifact:
    """Broad-press story-count overlay (ADR-042) — display/validation only."""

    dates: list[str]
    story_count: list[int]
    ratio: list[float]
    reliable_since_year: int
    caption: str


@dataclass
class MarketsArtifact:
    """FRED markets overlay + bidirectional Granger readout (ADR-041)."""

    series_id: str | None
    series_label: str | None
    dates: list[str]
    volume: list[float]
    market: list[float]
    granger: dict[str, Any]      # MarketsOverlay.granger_bidirectional() output
    caption: str


# ---------------------------------------------------------------------------
# Per-narrative artifact: narrative_<cluster_id>.json
# ---------------------------------------------------------------------------


@dataclass
class NarrativeArtifact:
    cluster_id: int
    label: str
    stage: Stage
    card: dict[str, Any]                         # StoryCard.to_dict()
    volume: SeriesArtifact
    fits: list[FitArtifact]
    staging_model: str                           # which fit the stage keys off
    shape_facts: dict[str, float]                # model-free (ADR-039)
    stage_detail: dict[str, Any]
    jel: JELArtifact | None = None
    similar: SimilarNarratives | None = None    # ADR-019 §H panel (ADR-044)
    mediacloud: MediaCloudArtifact | None = None
    markets: MarketsArtifact | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def filename(self) -> str:
        return f"narrative_{self.cluster_id}.json"


# ---------------------------------------------------------------------------
# Catalogue: index.json
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    """One row in the catalogue — enough for gallery cards, the map, the feed."""

    cluster_id: int
    label: str
    stage: Stage
    n_articles: int
    top_terms: list[str] = field(default_factory=list)
    peak_date: str | None = None
    date_range: tuple[str, str] | None = None
    in_scope: bool = True
    jel_code: str | None = None
    is_emerging: bool = False                    # 4-week recency flag (ADR-019)
    umap_xy: tuple[float, float] | None = None   # 2-D display projection (ADR-044)
    similar_edges: list[tuple[int, float]] = field(default_factory=list)
    # semantic top-k neighbors for the map graph: (neighbor_cluster_id, weight) (ADR-044)


@dataclass
class DashboardIndex:
    generated_at: str                            # ISO 8601 UTC
    global_random_seed: int
    stage_min_r0: float
    n_narratives: int
    narratives: list[IndexEntry] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
