"""Unit tests for per-document furniture cleaning (ADR-082)."""
from __future__ import annotations

from mnd.filtering.furniture import (
    FurnitureCleaner,
    split_byline_title,
    strip_attribution_preamble,
    strip_body_furniture,
    strip_leading_furniture,
    strip_pdf_furniture,
)


class TestLeadingFurniture:
    def test_strips_leading_date_stamp(self):
        # CBO cost-estimate pattern: "January 21, 2010 Cost Estimate …"
        body, changed = strip_leading_furniture(
            "January 21, 2010 Cost Estimate Cost estimate for the bill as ordered.",
            "S. 555, Sugar Loaf Fire Protection District Land Exchange Act",
        )
        assert changed and body.startswith("Cost Estimate")

    def test_strips_title_repeat_then_published_date(self):
        # OFR pattern: "Crash Narratives Published: December 28, 2023 The financial…"
        body, changed = strip_leading_furniture(
            "Crash Narratives Published: December 28, 2023 The financial press is a conduit.",
            "Crash Narratives",
        )
        assert changed and body.startswith("The financial press")

    def test_strips_iso_date(self):
        body, changed = strip_leading_furniture("2023-03-15 The committee met.", "Minutes")
        assert changed and body == "The committee met."

    def test_strips_editors_note_credit(self):
        body, changed = strip_leading_furniture(
            "Editors' note: This column first appeared in the eBook. The real argument begins here.",
            "A column",
        )
        assert changed and body.startswith("The real argument begins here")

    def test_inline_date_untouched(self):
        # A date mid-sentence is content, not lead furniture.
        text = "The crisis peaked on January 21, 2010 across markets worldwide."
        body, changed = strip_leading_furniture(text, "Crisis")
        assert not changed and body == text

    def test_partial_title_echo_not_stripped(self):
        # Body starts with words resembling the title but not a verbatim prefix.
        text = "Inflation and its discontents shaped the whole decade of policy."
        body, changed = strip_leading_furniture(text, "Inflation dynamics")
        assert not changed and body == text

    def test_title_as_sentence_subject_not_stripped(self):
        # PIIE case: the title IS the subject of the first sentence (lowercase
        # continuation) — stripping it would leave a fragment.
        text = ("Rebuilding the global economy is essential to addressing many "
                "interlocking problems at once, including the recovery.")
        body, changed = strip_leading_furniture(text, "Rebuilding the global economy")
        assert not changed and body == text

    def test_title_repeat_before_new_sentence_stripped(self):
        # NBER case: title noun-phrase then a new sentence (uppercase) — furniture.
        text = ("Private Equity and Industry Performance The growth of the private "
                "equity industry has spurred concerns about the economy.")
        body, changed = strip_leading_furniture(text, "Private Equity and Industry Performance")
        assert changed and body.startswith("The growth of the private equity")

    def test_leading_date_before_lowercase_kept(self):
        # A leading full date that is the sentence subject is not stripped.
        text = "January 21, 2010 was the day the crisis truly began in earnest."
        body, changed = strip_leading_furniture(text, "Crisis timeline")
        assert not changed and body == text

_BIS_TITLE = "Jean-Claude Trichet: Interview with FOCUS"
_BIS_BODY = (
    "Jean-Claude Trichet: Interview with FOCUS Interview with Mr Jean-Claude "
    "Trichet, President of the European Central Bank, in FOCUS, conducted by "
    "Ms A Writer, 27 January 2010. The euro area economy is recovering "
    "gradually. Price stability remains our primary mandate and inflation "
    "expectations are firmly anchored."
)


class TestBylineTitle:
    def test_splits_bis_byline_with_body_evidence(self):
        title, speaker = split_byline_title(_BIS_TITLE, _BIS_BODY)
        assert title == "Interview with FOCUS"
        assert speaker == "Jean-Claude Trichet"

    def test_ordinary_colon_title_untouched(self):
        # "Inflation: the road ahead" — prefix is not a name shape.
        t, s = split_byline_title("Inflation: the road ahead", "Any body text")
        assert s is None and t == "Inflation: the road ahead"

    def test_capitalized_non_name_prefix_untouched(self):
        t, s = split_byline_title(
            "Executive Summary: Financial Stability Report", "Executive Summary text"
        )
        assert s is None

    def test_name_without_body_evidence_untouched(self):
        # Name-shaped prefix but the body never mentions the surname → no split.
        t, s = split_byline_title(
            "Adam Smith: The Wealth of Nations", "A treatise about markets."
        )
        assert s is None

    def test_place_name_prefix_untouched(self):
        # Multi-word place names look name-shaped but introduce a subject.
        for title in ("New York: fiscal strain", "Hong Kong: capital outflows",
                      "South Korea: export slowdown"):
            _, s = split_byline_title(title, title.lower() + " continues to worsen")
            assert s is None, title


class TestAttributionPreamble:
    def test_strips_reprint_header(self):
        body, stripped = strip_attribution_preamble(_BIS_BODY, _BIS_TITLE)
        assert stripped
        assert body.startswith("The euro area economy is recovering")

    def test_plain_article_untouched(self):
        plain = "Inflation rose in March. The committee held rates steady."
        body, stripped = strip_attribution_preamble(plain, "Inflation update")
        assert not stripped and body == plain


class TestPdfFurniture:
    def test_drops_page_numbers_and_running_headers(self):
        lines = []
        for page in range(1, 5):
            lines.append("CBO Working Paper 2023-07")   # running header (4x)
            lines.append(f"Real content paragraph on page {page} discussing "
                         "federal outlays and deficits at reasonable length.")
            lines.append(str(page))                      # bare page number
        body = "\n".join(lines)
        cleaned, dropped, ref = strip_pdf_furniture(body)
        assert dropped == 8  # 4 headers + 4 page numbers
        assert "CBO Working Paper" not in cleaned
        assert "federal outlays" in cleaned

    def test_drops_trailing_reference_section_only_in_tail(self):
        body = "\n".join(
            [f"Substantive paragraph {i} about monetary policy." for i in range(10)]
            + ["References", "Smith, J. (2020). A paper. Journal.", "Doe, A. (2021)."]
        )
        cleaned, dropped, ref = strip_pdf_furniture(body)
        assert ref and "Smith, J." not in cleaned
        assert "Substantive paragraph 9" in cleaned

    def test_early_references_heading_kept(self):
        # A "References" line in the first 60% of the doc is not a tail.
        body = "\n".join(
            ["References", "are discussed early here."]
            + [f"Long substantive paragraph {i}." for i in range(20)]
        )
        cleaned, dropped, ref = strip_pdf_furniture(body)
        assert not ref

    def test_trailing_notes_section_dropped(self):
        body = "\n".join(
            [f"Substantive paragraph {i} on fiscal policy." for i in range(10)]
            + ["Notes", "1. See the appendix.", "2. Data from FRED."]
        )
        cleaned, dropped, ref = strip_body_furniture(body)
        assert ref and "Data from FRED" not in cleaned

    def test_metadata_and_citation_lines_dropped(self):
        body = "\n".join([
            "JEL classification: E52, E58",
            "Keywords: inflation, monetary policy",
            "The committee weighed labor market tightening against inflation.",
            "Households expected prices to keep rising through the year.",
            "https://www.example.org/paper.pdf",
            "Available at: https://ssrn.com/abstract=123",
            "media@centralbank.org",
        ])
        cleaned, dropped, _ = strip_body_furniture(body)
        assert "JEL classification" not in cleaned
        assert "Keywords:" not in cleaned
        assert "ssrn.com" not in cleaned and "media@centralbank.org" not in cleaned
        # Real prose with an inline colon or URL-like token is preserved.
        assert "labor market tightening" in cleaned
        assert "prices to keep rising" in cleaned

    def test_inline_keyword_mention_preserved(self):
        # Whole-line anchored: an inline "keywords" is not a metadata line.
        body = "\n".join([
            "The keywords investors watched were growth and inflation.",
            "Analysts parsed every statement for hints about the next move.",
            "The debate shaped borrowing costs across the economy over months.",
            "By year end the tightening cycle had clearly run its course here.",
        ])
        cleaned, dropped, _ = strip_body_furniture(body)
        assert dropped == 0 and "keywords investors watched" in cleaned


class _Article:
    def __init__(self, title, body, source_id, author=None):
        self.title, self.body, self.source_id, self.author = title, body, source_id, author


class TestCleaner:
    def test_end_to_end_bis_article(self):
        a = _Article(_BIS_TITLE, _BIS_BODY, "bis")
        cleaner = FurnitureCleaner(enabled=True)
        cleaner.clean([a])
        assert a.title == "Interview with FOCUS"
        assert a.author == "Jean-Claude Trichet"
        assert a.body.startswith("The euro area economy")
        assert cleaner.report.n_byline_titles_split == 1
        assert cleaner.report.n_preambles_stripped == 1

    def test_non_byline_source_body_still_defurnitured(self):
        body = "\n".join(
            ["OFR Brief 21-01"] * 3
            + [f"Paragraph {i} about repo market stress and dealer balance sheets." for i in range(6)]
        )
        a = _Article("Repo market stress", body, "treasury_ofr")
        FurnitureCleaner(enabled=True).clean([a])
        assert "OFR Brief 21-01" not in a.body
        assert "repo market stress" in a.body

    def test_existing_author_not_overwritten(self):
        a = _Article(_BIS_TITLE, _BIS_BODY, "bis", author="ECB Press Office")
        FurnitureCleaner(enabled=True).clean([a])
        assert a.author == "ECB Press Office"
