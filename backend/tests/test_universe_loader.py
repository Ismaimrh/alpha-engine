"""Unit tests for universe_loader (Step 3) — offline, fixture-based."""

from pathlib import Path

import pandas as pd
import pytest

from app.data_pipeline.universe_loader import normalize_ticker, parse_sp500_html

FIXTURE = Path(__file__).parent / "fixtures" / "sp500_wikipedia_sample.html"


@pytest.fixture(scope="module")
def parsed() -> pd.DataFrame:
    return parse_sp500_html(FIXTURE.read_text())


def test_normalize_ticker():
    assert normalize_ticker("BRK.B") == "BRK-B"
    assert normalize_ticker(" bf.b ") == "BF-B"
    assert normalize_ticker("AAPL") == "AAPL"


def test_parse_shape_and_columns(parsed):
    assert list(parsed.columns) == ["ticker", "name", "sector", "industry"]
    assert len(parsed) == 503


def test_share_class_tickers_normalized(parsed):
    tickers = set(parsed["ticker"])
    assert "BRK-B" in tickers and "BF-B" in tickers
    assert not any("." in t for t in tickers)


def test_no_duplicates_and_sorted(parsed):
    assert parsed["ticker"].is_unique
    assert list(parsed["ticker"]) == sorted(parsed["ticker"])


def test_picks_constituents_not_changes_table(parsed):
    # The fixture contains a second (changes) table; parser must skip it.
    assert "XYZ" not in set(parsed["ticker"])


def test_sanity_range_rejects_tiny_table():
    tiny = """<table><thead><tr><th>Symbol</th><th>Security</th>
    <th>GICS Sector</th><th>GICS Sub-Industry</th></tr></thead>
    <tbody><tr><td>AAPL</td><td>Apple</td><td>IT</td><td>Hardware</td></tr></tbody>
    </table>"""
    with pytest.raises(ValueError, match="sanity range"):
        parse_sp500_html(tiny)
