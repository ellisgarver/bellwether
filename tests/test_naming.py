"""Display-layer narrative naming (ADR-056).

Covers the cache-incremental contract: a stubbed client is called once per
cache miss, hits are served from the committed cache without the client, the
feature degrades to {} when disabled or unbuildable, and the cache key tracks
the representation + prompt/model knobs.
"""
from __future__ import annotations

import pytest

from mnd.dashboard import naming
from mnd.dashboard.naming import NamingInput, _build_user, _signature, generate_names


class StubClient:
    """Counts calls and returns a fixed name; stands in for AnthropicNamer."""

    def __init__(self) -> None:
        self.calls = 0

    def name_cluster(self, system, user, schema):
        self.calls += 1
        return {"title": f"Title {self.calls}", "description": "A neutral description."}


def _cfg(tmp_path, **over):
    nc = {
        "enabled": True,
        "model": "claude-haiku-4-5",
        "max_title_words": 6,
        "prompt_version": 1,
        "cache_dir": str(tmp_path / "naming_cache"),
    }
    nc.update(over)
    return {"display": {"naming": nc}}


def _inputs():
    return [
        NamingInput(0, ["inflation", "fomc", "rate"], ["The FOMC raised rates..."],
                    date_range=("2021-01-01", "2022-06-01"), sources=["fed_ny", "nber"]),
        NamingInput(1, ["basel", "capital", "bank"], ["Basel III capital rules..."]),
    ]


def test_generates_and_caches(tmp_path):
    client = StubClient()
    names = generate_names(_inputs(), _cfg(tmp_path), client=client)
    assert set(names) == {0, 1}
    assert names[0].title and names[0].description
    assert client.calls == 2  # one call per cluster on the cold cache


def test_cache_hit_skips_client(tmp_path):
    cfg = _cfg(tmp_path)
    first = StubClient()
    generate_names(_inputs(), cfg, client=first)
    assert first.calls == 2

    # Second run with a fresh client that must never be called — all served from cache.
    second = StubClient()
    names = generate_names(_inputs(), cfg, client=second)
    assert second.calls == 0
    assert set(names) == {0, 1}


def test_disabled_returns_empty(tmp_path):
    names = generate_names(_inputs(), _cfg(tmp_path, enabled=False), client=StubClient())
    assert names == {}


def test_degrades_when_client_unbuildable(tmp_path, monkeypatch):
    # No injected client and construction fails (no SDK/key) → fall back, no crash.
    def boom(cfg):
        raise RuntimeError("no anthropic client")

    monkeypatch.setattr(naming.AnthropicNamer, "from_config", classmethod(lambda cls, cfg: boom(cfg)))
    names = generate_names(_inputs(), _cfg(tmp_path), client=None)
    assert names == {}


def test_later_failure_keeps_earlier_clusters(tmp_path):
    # A failure *after* a success is treated as a one-off bad cluster: the earlier
    # name is kept, the failing one is simply absent (not an abort).
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def name_cluster(self, system, user, schema):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("model error")
            return {"title": "Recovered", "description": "ok"}

    names = generate_names(_inputs(), _cfg(tmp_path), client=FlakyClient())
    assert len(names) == 1  # cluster 0 resolved; cluster 1 failed and is absent


def test_first_failure_aborts(tmp_path):
    # The first call failing is read as systemic (auth/config) → abort, all fall back.
    class DeadClient:
        def __init__(self):
            self.calls = 0

        def name_cluster(self, system, user, schema):
            self.calls += 1
            raise RuntimeError("401")

    dead = DeadClient()
    names = generate_names(_inputs(), _cfg(tmp_path), client=dead)
    assert names == {}
    assert dead.calls == 1  # aborted after the first failure, did not hammer the rest


def test_signature_tracks_representation_and_knobs():
    a = NamingInput(0, ["inflation"], ["x"])
    b = NamingInput(0, ["inflation"], ["x"])
    assert _signature(a, "m", 1, 6) == _signature(b, "m", 1, 6)
    # any representation or knob change yields a new key
    assert _signature(a, "m", 1, 6) != _signature(NamingInput(0, ["deflation"], ["x"]), "m", 1, 6)
    assert _signature(a, "m", 1, 6) != _signature(a, "m", 2, 6)   # prompt_version
    assert _signature(a, "m", 1, 6) != _signature(a, "other", 1, 6)  # model


def test_prompt_is_grounded_in_supplied_material():
    user = _build_user(_inputs()[0], 6)
    assert "inflation" in user and "fomc" in user
    assert "FOMC raised rates" in user
    # anchor names must not leak into the prompt (no-tuning discipline, ADR-040)
    assert "SVB" not in user and "taper tantrum" not in user.lower()


@pytest.mark.parametrize(
    "raw, expected",
    [
        # first-letter capital + acronym up-casing (pre-existing behavior)
        ("gdp and inflation dynamics", "GDP and inflation dynamics"),
        ("detroit municipal finance", "Detroit municipal finance"),
        # proper nouns mid-title: countries, demonyms, cities, institutions
        ("south sudan crisis and african politics", "South Sudan crisis and African politics"),
        ("chinas real estate market adjustment", "China's real estate market adjustment"),
        ("low interest rates and german savers", "Low interest rates and German savers"),
        # apostrophe-less possessive: capitalize the name, but never invent an apostrophe
        ("trichets speeches on eurozone stability", "Trichets speeches on eurozone stability"),
        ("ieepa tariffs supreme court", "IEEPA tariffs Supreme Court"),
        ("cross-strait relations with china", "Cross-strait relations with China"),
        # glued country pairs recover via hyphen split; ordinary hyphenates don't
        ("us-india relations under modi", "US-India relations under Modi"),
        ("bank of japan monetary easing", "Bank of Japan monetary easing"),
        # possessive on a proper noun is preserved and capitalized
        ("iran's nuclear program", "Iran's nuclear program"),
        # multi-word fixups win before per-word handling
        ("european union budget rules", "European Union budget rules"),
        # trailing date spans are dropped (shown separately on every card)
        ("iran sanctions on uav production, 2010-2026", "Iran sanctions on UAV production"),
        ("sanctions against syria, 2011-2024", "Sanctions against Syria"),
        ("north korea summit diplomacy 2018", "North Korea summit diplomacy"),
        ("emerging economies' monetary challenges 2022-23", "Emerging economies' monetary challenges"),
        ("nafta renegotiation, 2017", "NAFTA renegotiation"),
        # models sometimes glue the two years with no separator
        ("journalism in washington 19782012", "Journalism in Washington"),
        # a meaningful leading year and non-year digits are preserved
        ("2013 taper tantrum", "2013 taper tantrum"),
        ("covid-19 market response", "COVID-19 market response"),
    ],
)
def test_polish_title_capitalizes_proper_nouns(raw, expected):
    from mnd.dashboard.naming import _polish_title

    assert _polish_title(raw) == expected


def test_polish_title_leaves_common_words_lowercase():
    """The proper-noun list must not touch ordinary vocabulary (sentence case)."""
    from mnd.dashboard.naming import _polish_title

    assert _polish_title("bond market liquidity and funding stress") == (
        "Bond market liquidity and funding stress"
    )


def test_signature_stable_across_date_span_extension():
    """ADR-070: a continuing narrative's weekly-extending span must not
    invalidate its cached title; only substance changes may."""
    from mnd.dashboard.naming import NamingInput, _signature

    base = dict(cluster_id=1, terms=["a", "b"], excerpts=["x"], sources=["fed"])
    s1 = _signature(NamingInput(**base, date_range=("2020-01-01", "2026-06-01")), "m", 2, 7)
    s2 = _signature(NamingInput(**base, date_range=("2020-01-01", "2026-07-06")), "m", 2, 7)
    assert s1 == s2
    s3 = _signature(
        NamingInput(cluster_id=1, terms=["a", "CHANGED"], excerpts=["x"], sources=["fed"],
                    date_range=("2020-01-01", "2026-07-06")),
        "m", 2, 7,
    )
    assert s3 != s1
