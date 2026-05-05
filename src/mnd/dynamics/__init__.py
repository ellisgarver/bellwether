"""Dynamics fitting: ODE models, smoothing, normalization, and calendar annotation."""

from mnd.dynamics.fitting import ClusterDynamics, DynamicsFitter, FitResult
from mnd.dynamics.models import (
    aicc,
    exponential,
    gompertz,
    logistic,
    logistic_r0,
    sir_prevalence,
    sir_r0,
)
from mnd.dynamics.normalize import normalize_cluster_volumes, compute_source_contamination
from mnd.dynamics.smooth import smooth_stratified, TIER_SOURCES
from mnd.dynamics.calendar import CalendarAnnotator

__all__ = [
    "DynamicsFitter",
    "FitResult",
    "ClusterDynamics",
    "logistic",
    "gompertz",
    "exponential",
    "sir_prevalence",
    "logistic_r0",
    "sir_r0",
    "aicc",
    "normalize_cluster_volumes",
    "compute_source_contamination",
    "smooth_stratified",
    "TIER_SOURCES",
    "CalendarAnnotator",
]
