"""Dashboard stage: bakes the analysis layer into the JSON artifacts the site reads (ADR-043)."""

from mnd.dashboard.build_artifacts import (
    build_dashboard_artifacts,
    write_dashboard_artifacts,
)
from mnd.dashboard.story_card import StoryCard, build_all_cards, build_story_card

__all__ = [
    "StoryCard",
    "build_all_cards",
    "build_story_card",
    "build_dashboard_artifacts",
    "write_dashboard_artifacts",
]
