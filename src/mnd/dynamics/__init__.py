"""Dynamics fitting: closed-form lens models, smoothing, normalization, calendar."""

from mnd.dynamics.fitting import ClusterDynamics, DynamicsFitter, FitResult
from mnd.dynamics.models import (
    aicc,
    bass,
    bass_peak_time,
    logistic,
    logistic_doubling_time,
    shape_facts,
    sir_decay_rate,
    sir_kssir_curve,
    sir_rise_rate,
)
from mnd.dynamics.normalize import (
    adjusted_cluster_volumes,
    compute_source_contamination,
    corpus_base_rate,
)
from mnd.dynamics.smooth import smooth_combined
from mnd.dynamics.calendar import CalendarAnnotator

__all__ = [
    "DynamicsFitter",
    "FitResult",
    "ClusterDynamics",
    "logistic",
    "sir_kssir_curve",
    "sir_rise_rate",
    "sir_decay_rate",
    "bass",
    "bass_peak_time",
    "shape_facts",
    "logistic_doubling_time",
    "aicc",
    "corpus_base_rate",
    "adjusted_cluster_volumes",
    "compute_source_contamination",
    "smooth_combined",
    "CalendarAnnotator",
]
