"""Offline tests for the congressional trading loader (Step 5.4)."""

from datetime import date

import pytest

from app.data_pipeline.congress_loader import (
    normalize_rows,
    normalize_type,
    parse_amount_range,
    row_key,
    staleness,
)


def test_parse_amount_range_midpoint():
    value, rng = parse_amount_range("$1,001 - $15,000")
    assert value == pytest.approx(8000.5)
    assert rng == "$1,001 - $15,000"


def test_parse_amount_range_open_ended():
    value, _ = parse_amount_range("Over $50,000,000")
    assert value == 50_000_000.0
    value, _ = parse_amount_range("$1,001 -")
    assert value == 1001.0


def test_parse_amount_range_garbage():
    assert parse_amount_range(None) == (None, None)
    assert parse_amount_range("Unknown") == (None, "Unknown")


def test_normalize_type():
    assert normalize_type("Purchase") == "purchase"
    assert normalize_type("sale_full") == "sale"
    assert normalize_type("Sale (Partial)") == "sale"
    assert normalize_type("Exchange") == "exchange"
    assert normalize_type("weird") is None
    assert normalize_type(None) is None


def _senate_rows() -> list[dict]:
    return [
        {  # valid purchase, senate date format MM/DD/YYYY
            "transaction_date": "01/15/2026", "disclosure_date": "02/01/2026",
            "ticker": "AAPL", "type": "Purchase",
            "amount": "$15,001 - $50,000", "senator": "Jane Doe",
        },
        {  # BRK.B -> BRK-B normalization
            "transaction_date": "01/20/2026", "disclosure_date": "02/05/2026",
            "ticker": "BRK.B", "type": "Sale (Full)",
            "amount": "$1,001 - $15,000", "senator": "John Roe",
        },
        {  # no ticker -> skipped
            "transaction_date": "01/22/2026", "disclosure_date": "02/06/2026",
            "ticker": "--", "type": "Purchase",
            "amount": "$1,001 - $15,000", "senator": "Jane Doe",
        },
        {  # unparseable date -> skipped
            "transaction_date": "n/a", "disclosure_date": "02/07/2026",
            "ticker": "MSFT", "type": "Purchase",
            "amount": "$1,001 - $15,000", "senator": "Jane Doe",
        },
    ]


def test_normalize_rows_senate():
    rows = normalize_rows(_senate_rows(), "Senate")
    assert len(rows) == 2  # two skipped
    first = rows[0]
    assert first["ticker"] == "AAPL"
    assert first["transaction_date"] == "2026-01-15"
    assert first["filing_date"] == "2026-02-01"
    assert first["chamber"] == "Senate"
    assert first["transaction_type"] == "purchase"
    assert first["estimated_value"] == pytest.approx(32500.5)
    assert rows[1]["ticker"] == "BRK-B"


def test_normalize_rows_house_iso_dates_and_field():
    house = [{
        "transaction_date": "2026-03-10", "disclosure_date": "03/25/2026",
        "ticker": "NVDA", "type": "purchase",
        "amount": "$50,001 - $100,000", "representative": "Rep Example",
    }]
    rows = normalize_rows(house, "House")
    assert rows[0]["politician_name"] == "Rep Example"
    assert rows[0]["chamber"] == "House"
    assert rows[0]["transaction_date"] == "2026-03-10"


def test_row_key_deterministic_and_distinct():
    k1 = row_key("Senate", "Jane Doe", "AAPL", "2026-01-15", "purchase",
                 "$1,001 - $15,000", "2026-02-01")
    k2 = row_key("Senate", "Jane Doe", "AAPL", "2026-01-15", "purchase",
                 "$1,001 - $15,000", "2026-02-01")
    k3 = row_key("Senate", "Jane Doe", "AAPL", "2026-01-16", "purchase",
                 "$1,001 - $15,000", "2026-02-01")
    assert k1 == k2 != k3


def test_staleness_detection():
    fresh = [{"filing_date": date.today().isoformat()}]
    newest, stale = staleness(fresh)
    assert not stale and newest == date.today()

    old = [{"filing_date": "2025-01-01"}]
    newest, stale = staleness(old, today=date(2026, 7, 8))
    assert stale and newest == date(2025, 1, 1)

    assert staleness([]) == (None, True)


def test_dedupe_row_keys_identical_trades_kept_distinct():
    from app.data_pipeline.congress_loader import dedupe_row_keys

    k = row_key("Senate", "Jane Doe", "AAPL", "2026-01-15", "purchase",
                "$1,001 - $15,000", "2026-02-01")
    records = [{"row_key": k, "n": 1}, {"row_key": k, "n": 2},
               {"row_key": k, "n": 3}, {"row_key": "other", "n": 4}]
    out = dedupe_row_keys([dict(r) for r in records])
    keys = [r["row_key"] for r in out]
    assert len(set(keys)) == 4          # all unique now
    assert keys[0] == k                 # first occurrence unchanged
    assert keys[3] == "other"           # non-duplicates untouched
    # Deterministic: same input -> same disambiguated keys
    again = dedupe_row_keys([dict(r) for r in records])
    assert [r["row_key"] for r in again] == keys
