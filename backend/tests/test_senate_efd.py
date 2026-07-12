"""Offline tests for the Senate EFD loader (Plan B, Step 5.4)."""

from pathlib import Path

import pytest

from app.data_pipeline.congress_loader import normalize_rows
from app.data_pipeline.senate_efd_loader import (
    extract_csrf,
    parse_listing_row,
    parse_ptr_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_csrf():
    html = (FIXTURES / "efd_landing_sample.html").read_text()
    assert extract_csrf(html) == "Abc123TokenXYZ"


def test_extract_csrf_missing_raises_actionable():
    with pytest.raises(RuntimeError, match="markup may"):
        extract_csrf("<html><body>nothing here</body></html>")


def test_parse_listing_row_electronic_and_paper():
    e = parse_listing_row(
        ["JOHN", "DOE", "<span>Senator</span>",
         '<a href="/search/view/ptr/abcd-1234-ef/">PTR 07/01/2026</a>',
         "07/01/2026"]
    )
    assert e["kind"] == "ptr" and e["uuid"] == "abcd-1234-ef"
    assert e["senator"] == "John Doe"
    assert e["url"].endswith("/search/view/ptr/abcd-1234-ef/")

    p = parse_listing_row(
        ["JANE", "ROE", "<span>Senator</span>",
         '<a href="/search/view/paper/9999-aaaa/">PTR (paper)</a>',
         "06/15/2026"]
    )
    assert p["kind"] == "paper"

    assert parse_listing_row(["too", "short"]) is None
    assert parse_listing_row(["A", "B", "C", "no link here", "d"]) is None


def test_parse_ptr_html_rows():
    html = (FIXTURES / "efd_ptr_sample.html").read_text()
    rows = parse_ptr_html(html, "John Doe", "07/01/2026")
    assert len(rows) == 3
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["type"] == "Purchase"
    assert rows[0]["amount"] == "$15,001 - $50,000"
    assert rows[0]["disclosure_date"] == "07/01/2026"
    assert rows[0]["senator"] == "John Doe"


def test_ptr_rows_flow_through_existing_normalizer():
    """EFD output must be drop-in compatible with congress_loader's
    normalize_rows — the whole point of Plan B's design."""
    html = (FIXTURES / "efd_ptr_sample.html").read_text()
    raw = parse_ptr_html(html, "John Doe", "07/01/2026")
    normalized = normalize_rows(raw, "Senate")
    # Row 3 has ticker '--' -> centrally skipped
    assert len(normalized) == 2
    assert normalized[0]["ticker"] == "AAPL"
    assert normalized[0]["transaction_date"] == "2026-06-10"
    assert normalized[0]["filing_date"] == "2026-07-01"
    assert normalized[0]["transaction_type"] == "purchase"
    assert normalized[1]["ticker"] == "BRK-B"        # dot normalized
    assert normalized[1]["transaction_type"] == "sale"
    assert all(r["chamber"] == "Senate" and r["row_key"] for r in normalized)


def test_parse_ptr_html_no_table():
    assert parse_ptr_html("<html><body>paper scan</body></html>", "X", "Y") == []


def test_tier1_403_raises_actionable_selenium_hint(monkeypatch):
    import app.data_pipeline.senate_efd_loader as mod

    class Fake403:
        status_code = 403
        def raise_for_status(self):  # pragma: no cover
            raise AssertionError("should not reach raise_for_status")

    class FakeSession:
        headers = {}
        def get(self, url, timeout=30):
            return Fake403()

    monkeypatch.setattr(mod.requests, "Session", FakeSession)
    with pytest.raises(RuntimeError, match="--engine selenium"):
        mod.open_session()


def test_browser_headers_look_like_a_browser():
    from app.data_pipeline.senate_efd_loader import BROWSER_HEADERS
    assert BROWSER_HEADERS["User-Agent"].startswith("Mozilla/5.0")
    assert "Accept-Language" in BROWSER_HEADERS
