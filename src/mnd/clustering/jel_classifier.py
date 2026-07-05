"""Post-clustering JEL classification (ADR-020).

Each BERTopic cluster is assigned a primary JEL (Journal of Economic
Literature) code by comparing its representation against the official
AEA-published descriptions of every top-level JEL category. The
representation is the cluster's c-TF-IDF top terms enriched with its
BERTopic representative-document text (ADR-055). The macro-finance scope
({E, F, G, H} by config) is a per-narrative **display flag, not a gate**
(ADR-046): every non-noise cluster above the fit floor is fit, staged, and
shown; out-of-scope clusters are flagged with their code, never dropped.

This replaces the pre-clustering JEL keyword filter (deleted by ADR-020).
The methodological rationale:
  - The basis-set source selection is already a coarse macro-content filter.
  - Adding a 213-keyword pre-clustering gate on top added researcher
    judgment over which keywords represent each JEL code — exactly the
    kind of decision that's costly to defend in pre-registration.
  - JEL is a published, externally-maintained taxonomy. Embedding the
    AEA's own descriptions as classifier prototypes and applying them at
    the cluster level (where there's enough content to support a robust
    classification) is symmetric across sources, free of researcher
    keyword choices, and uses the same embedding space as the clustering
    itself.

Public surface:

    >>> from mnd.clustering.jel_classifier import classify_clusters
    >>> assignments = classify_clusters(
    ...     cluster_terms={0: ["inflation", "fomc", "rate"], 1: ["lasik", "surgery"]},
    ...     embedder=embedder,
    ... )
    >>> assignments[0].primary_code
    'E'
    >>> assignments[0].in_scope
    True
    >>> assignments[1].in_scope
    False

Output schema is stable; downstream code reads (cluster_id, primary_code,
in_scope) as a display flag — out-of-scope narratives are surfaced with
their code, not filtered out of dynamics (ADR-046).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from mnd.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Reference taxonomy
# ---------------------------------------------------------------------------
# Top-level JEL codes and their official AEA descriptions. Verbatim from
# https://www.aeaweb.org/econlit/jelCodes.php (American Economic Association,
# accessed 2026-05-20). Updating this requires a new ADR — the descriptions
# are the field's published taxonomy, not researcher commentary.

JEL_CODE_DESCRIPTIONS: dict[str, str] = {
    "A": (
        "General Economics and Teaching. General economics, teaching of economics, "
        "economics of education at all levels, relation of economics to other "
        "disciplines, economic methodology."
    ),
    "B": (
        "History of Economic Thought, Methodology, and Heterodox Approaches. "
        "Schools of economic thought, history of economic thought, methodology, "
        "current heterodox approaches."
    ),
    "C": (
        "Mathematical and Quantitative Methods. Econometric and statistical methods, "
        "mathematical methods, modeling, simulation methods, design of experiments."
    ),
    "D": (
        "Microeconomics. Household behavior, consumer economics, production and "
        "organizations, market structure and pricing, game theory and bargaining, "
        "information, knowledge and uncertainty, welfare economics, intertemporal "
        "choice, behavioral microeconomics, microeconomics of analysis of collective "
        "decision-making."
    ),
    "E": (
        "Macroeconomics and Monetary Economics. Macroeconomic aggregates, consumption, "
        "saving, production, investment, business cycles, inflation, prices, wages, "
        "employment, unemployment, monetary policy, central banking, money supply, "
        "interest rates, money and credit, macroeconomic policy, macroeconomic "
        "forecasting and simulation."
    ),
    "F": (
        "International Economics. Trade, international factor movements, international "
        "business, balance of payments, finance, foreign exchange, international "
        "monetary arrangements, sovereign debt, international policy coordination, "
        "open-economy macroeconomics, international migration, multinational firms."
    ),
    "G": (
        "Financial Economics. General financial markets, financial institutions and "
        "services, corporate finance and governance, household finance, capital and "
        "ownership structure, banking, insurance, asset pricing, financial crises, "
        "international financial markets, market microstructure, behavioral finance, "
        "regulation of financial markets."
    ),
    "H": (
        "Public Economics. Structure and scope of government, taxation, subsidies, "
        "tax evasion, expenditures, fiscal policies, public goods, externalities, "
        "national budget, deficit, debt, intergovernmental relations, federalism, "
        "secession, state and local government, fiscal multipliers."
    ),
    "I": (
        "Health, Education, and Welfare. Health, education, welfare, poverty, "
        "well-being, public health, healthcare policy, educational attainment, "
        "social safety net programs."
    ),
    "J": (
        "Labor and Demographic Economics. Demographic economics, time allocation, "
        "work behavior, labor demand and supply, wages, compensation, labor costs, "
        "particular labor markets, mobility, unemployment, vacancies, immigrant "
        "workers, labor-management relations, labor unions, collective bargaining, "
        "discrimination, economics of minorities, races, indigenous peoples, "
        "non-labor discrimination."
    ),
    "K": (
        "Law and Economics. Basic areas of law, regulation and business law, "
        "antitrust law, contract law, illegal behavior and the enforcement of law, "
        "litigation process."
    ),
    "L": (
        "Industrial Organization. Market structure, firm strategy, market "
        "performance, firm objectives, organization, behavior, non-profit "
        "organizations, public enterprises, regulation and industrial policy, "
        "industry studies, manufacturing, services, transportation, energy."
    ),
    "M": (
        "Business Administration and Business Economics, Marketing, Accounting, "
        "Personnel Economics. Business administration, marketing, advertising, "
        "accounting, auditing, personnel and human resource management."
    ),
    "N": (
        "Economic History. Macroeconomic and monetary history, financial markets "
        "and institutions history, labor and consumer history, government policy "
        "history, regulation and business history, agriculture, natural resources, "
        "environment and extractive industries history."
    ),
    "O": (
        "Economic Development, Innovation, Technological Change, and Growth. "
        "Economic development, innovation, technological change, research and "
        "development, intellectual property rights, economic growth and aggregate "
        "productivity, economic planning and policy, regional development planning."
    ),
    "P": (
        "Economic Systems. Capitalist systems, socialist systems and transitional "
        "economies, planning, coordination, reform, other economic systems, "
        "comparative economic systems."
    ),
    "Q": (
        "Agricultural and Natural Resource Economics; Environmental and Ecological "
        "Economics. Agriculture, renewable resources and conservation, nonrenewable "
        "resources and conservation, energy, environmental economics, global warming, "
        "climate change."
    ),
    "R": (
        "Urban, Rural, Regional, Real Estate, and Transportation Economics. "
        "General regional economics, household analysis, production analysis and firm "
        "location, regional government analysis, real estate markets, spatial "
        "production and pricing, transportation economics."
    ),
    "Y": (
        "Miscellaneous Categories."
    ),
    "Z": (
        "Other Special Topics. Cultural economics, economic sociology, economic "
        "anthropology, religion, tourism economics, sports economics."
    ),
}

# Macro-finance scope per ADR-020. Clusters whose primary JEL code is in this
# set are retained for SIR/logistic dynamics analysis. Out-of-scope clusters
# are reported but excluded from fitting — they are not dropped from the
# embedded corpus.
DEFAULT_MACRO_JEL_SCOPE: frozenset[str] = frozenset({"E", "F", "G", "H"})


@dataclass(frozen=True)
class ClusterJELAssignment:
    """Result of JEL classification for one BERTopic cluster.

    cluster_id      The BERTopic cluster ID (-1 = outlier bucket).
    primary_code    The single best-fitting top-level JEL code.
    similarity      Cosine similarity of the cluster prototype to the
                    primary JEL prototype, in [-1, 1]. Higher = more
                    confident.
    runner_up       Code of the second-best match — for downstream
                    sensitivity analysis.
    runner_up_gap   primary_similarity - runner_up_similarity. Small gaps
                    indicate ambiguous classification.
    in_scope        Whether primary_code is in the macro-finance scope.
    """

    cluster_id: int
    primary_code: str
    similarity: float
    runner_up: str
    runner_up_gap: float
    in_scope: bool


class _Embedder(Protocol):
    """Minimal interface used by classify_clusters.

    Implemented by mnd.embedding.embedder.Embedder. The protocol allows
    tests to inject a stub.
    """

    def encode(self, texts: list[str], show_progress: bool = ...) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_clusters(
    cluster_terms: dict[int, list[str]],
    *,
    embedder: _Embedder | None = None,
    macro_scope: frozenset[str] = DEFAULT_MACRO_JEL_SCOPE,
    jel_descriptions: dict[str, str] | None = None,
    cluster_vectors: dict[int, np.ndarray] | None = None,
    prototype_vectors: np.ndarray | None = None,
) -> dict[int, ClusterJELAssignment]:
    """Assign a primary JEL code to each cluster by nearest-prototype.

    Each cluster is represented by its c-TF-IDF top terms (the BERTopic
    convention for cluster representation, Grootendorst 2022). Each JEL
    code is represented by the AEA's published description. Both are
    embedded with the same Qwen3 model used for the clustering itself,
    and cluster→JEL assignment is by maximum cosine similarity.

    Parameters
    ----------
    cluster_terms
        Mapping of cluster_id → list of c-TF-IDF top terms (typically the
        top 10-20 from ``BERTopic.get_topic(cluster_id)``).
    embedder
        Object implementing ``.encode(texts) -> np.ndarray``. Use the
        same Qwen3 embedder that produced the clustering input.
    macro_scope
        Set of top-level JEL codes considered in-scope for dynamics
        analysis. Defaults to {E, F, G, H} per ADR-020. Override only
        with a new ADR.
    jel_descriptions
        Override for the JEL prototype text. Defaults to
        ``JEL_CODE_DESCRIPTIONS``. The AEA's descriptions; do not edit
        without an ADR.

    Returns
    -------
    Mapping cluster_id → ClusterJELAssignment. The BERTopic outlier
    bucket (cluster_id = -1) is included if present in ``cluster_terms``;
    callers typically exclude it from dynamics analysis regardless of
    in_scope (outliers are by construction noise).
    """
    if jel_descriptions is None:
        jel_descriptions = JEL_CODE_DESCRIPTIONS
    codes: list[str] = sorted(jel_descriptions.keys())

    # JEL prototypes: use precomputed vectors when given (ADR-067 caches them so the
    # 8B embedder need not load on a re-run), else embed the AEA descriptions once.
    if prototype_vectors is not None:
        proto_vecs = _l2_normalize(np.asarray(prototype_vectors, dtype=float))
    else:
        proto_vecs = _l2_normalize(
            embedder.encode([jel_descriptions[c] for c in codes], show_progress=False)
        )

    # Cluster representation: use the precomputed cluster centroids when given
    # (ADR-067 — the same embeddings.npy centroids used for the map, no re-encode),
    # else embed the c-TF-IDF term joinder.
    if cluster_vectors is not None:
        cluster_ids = list(cluster_vectors.keys())
        cluster_vecs = _l2_normalize(
            np.vstack([np.asarray(cluster_vectors[cid], dtype=float) for cid in cluster_ids])
        )
    elif cluster_terms:
        cluster_ids = list(cluster_terms.keys())
        cluster_texts = [" ".join(cluster_terms[cid]) for cid in cluster_ids]
        cluster_vecs = _l2_normalize(embedder.encode(cluster_texts, show_progress=False))
    else:
        return {}

    # Cosine similarity matrix: (n_clusters, n_codes)
    sims = cluster_vecs @ proto_vecs.T

    assignments: dict[int, ClusterJELAssignment] = {}
    for i, cid in enumerate(cluster_ids):
        row = sims[i]
        order = np.argsort(-row)
        primary_idx = int(order[0])
        runner_idx = int(order[1]) if len(order) > 1 else primary_idx
        primary_code = codes[primary_idx]
        runner_code = codes[runner_idx]
        primary_sim = float(row[primary_idx])
        runner_sim = float(row[runner_idx])
        assignments[cid] = ClusterJELAssignment(
            cluster_id=cid,
            primary_code=primary_code,
            similarity=primary_sim,
            runner_up=runner_code,
            runner_up_gap=primary_sim - runner_sim,
            in_scope=primary_code in macro_scope,
        )

    n_in_scope = sum(1 for a in assignments.values() if a.in_scope)
    log.info(
        "JEL classification: %d/%d clusters in macro scope (codes %s); "
        "median runner-up gap = %.3f",
        n_in_scope, len(assignments), sorted(macro_scope),
        float(np.median([a.runner_up_gap for a in assignments.values()])),
    )
    return assignments


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization. Zero rows are left as-is (returns zero)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms
