"""Offline tests for the SEC Form 4 loader (Step 5.3) — fixture-based."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.data_pipeline import sec_form4_loader as mod
from app.data_pipeline.sec_form4_loader import list_form4_filings, parse_form4

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def rows():
    return parse_form4((FIXTURES / "form4_sample.xml").read_text())


def test_parse_extracts_p_and_s_only(rows):
    assert len(rows) == 2  # G-coded gift skipped
    assert [r["transaction_code"] for r in rows] == ["P", "S"]


def test_parse_buy_row_values(rows):
    buy = rows[0]
    assert buy["transaction_date"] == "2026-06-15"
    assert buy["shares"] == 10000
    assert buy["price"] == 152.50
    assert buy["total_value"] == pytest.approx(1_525_000.0)
    assert buy["insider_name"] == "DOE JANE"
    assert buy["insider_title"] == "Chief Financial Officer"


def test_parse_ignores_derivative_table(rows):
    # The derivative option 'P' (99999 shares) must NOT appear.
    assert all(r["shares"] != 99999 for r in rows)


def test_parse_handles_missing_officer_title():
    xml = (FIXTURES / "form4_sample.xml").read_text()
    xml = xml.replace(
        "<officerTitle>Chief Financial Officer</officerTitle>", ""
    ).replace("<isOfficer>1</isOfficer>", "<isOfficer>1</isOfficer>")
    parsed = parse_form4(xml)
    assert parsed[0]["insider_title"] == "Officer"  # falls back to flag


def _fake_submissions() -> dict:
    return {
        "filings": {
            "recent": {
                "form": ["4", "10-K", "4", "4"],
                "accessionNumber": [
                    "0001-26-000004", "0001-26-000003",
                    "0001-26-000002", "0001-26-000001",
                ],
                "filingDate": ["2026-06-16", "2026-03-01", "2025-11-10", "2024-01-05"],
                "primaryDocument": [
                    "xslF345X05/wk-form4_1.xml", "a10k.htm",
                    "form4_2.xml", "form4_old.xml",
                ],
            }
        }
    }


def test_list_form4_filings_filters_and_covers():
    class FakeResp:
        def json(self):
            return _fake_submissions()

    with patch.object(mod, "_get", return_value=FakeResp()):
        filings, covered = list_form4_filings(cik=320193, since=date(2025, 1, 1))
    assert [f["accession"] for f in filings] == ["0001-26-000004", "0001-26-000002"]
    assert filings[0]["filing_date"] == date(2026, 6, 16)
    assert covered is True  # oldest listed (2024-01-05) predates `since`

    with patch.object(mod, "_get", return_value=FakeResp()):
        _, covered_narrow = list_form4_filings(cik=320193, since=date(2023, 1, 1))
    assert covered_narrow is False  # window extends past the recent block


def test_headers_reject_placeholder_user_agent(monkeypatch):
    monkeypatch.setattr(mod, "SEC_USER_AGENT", '"Your Name your.email@example.com"')
    with pytest.raises(RuntimeError, match="fair-access"):
        mod._headers()
    monkeypatch.setattr(mod, "SEC_USER_AGENT", None)
    with pytest.raises(RuntimeError, match="fair-access"):
        mod._headers()
    monkeypatch.setattr(mod, "SEC_USER_AGENT", "Ismail X ismail@example.org")
    assert mod._headers()["User-Agent"].startswith("Ismail")


def test_checkpoint_roundtrip_and_atomicity(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", tmp_path / "cp.json")
    assert mod.load_checkpoint() == {}          # absent -> empty
    mod.save_checkpoint({"AAPL": "2026-07-08"})
    assert mod.load_checkpoint() == {"AAPL": "2026-07-08"}
    assert not (tmp_path / "cp.json.tmp").exists()  # temp cleaned by rename
    (tmp_path / "cp.json").write_text("{corrupted")
    assert mod.load_checkpoint() == {}          # corrupt -> empty, not crash


def test_backfill_skips_checkpointed_and_retries_errors(monkeypatch, tmp_path):
    """AAPL checkpointed today -> skipped; MSFT errors -> NOT checkpointed."""
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", tmp_path / "cp.json")
    today = date.today().isoformat()
    mod.save_checkpoint({"AAPL": today})

    import app.data_pipeline.yfinance_loader as yfl
    monkeypatch.setattr(yfl, "get_ticker_to_id",
                        lambda: {"AAPL": "id-a", "MSFT": "id-m"})
    monkeypatch.setattr(yfl, "log_quality", lambda rows: None)
    monkeypatch.setattr(mod, "load_ticker_cik_map",
                        lambda refresh=False: {"AAPL": 1, "MSFT": 2})

    calls = []
    def boom(cik, since):
        calls.append(cik)
        raise RuntimeError("simulated SEC failure")
    monkeypatch.setattr(mod, "list_form4_filings", boom)

    summary = mod.backfill_insider()
    assert summary["tickers_skipped_checkpoint"] == 1   # AAPL skipped
    assert calls == [2]                                 # only MSFT hit SEC
    assert summary["tickers_error"] == 1
    assert mod.load_checkpoint() == {"AAPL": today}     # MSFT NOT checkpointed


def test_timezone_suffixed_dates_are_sanitized():
    """PTC production bug: transactionDate '2026-05-12-05:00' must become
    '2026-05-12', not crash Postgres."""
    xml = (FIXTURES / "form4_sample.xml").read_text()
    xml = xml.replace(
        "<transactionDate><value>2026-06-15</value></transactionDate>",
        "<transactionDate><value>2026-06-15-05:00</value></transactionDate>",
    )
    rows = parse_form4(xml)
    assert rows[0]["transaction_date"] == "2026-06-15"

    # Truly garbage dates -> row skipped, not crashed
    xml_bad = (FIXTURES / "form4_sample.xml").read_text().replace(
        "<transactionDate><value>2026-06-15</value></transactionDate>",
        "<transactionDate><value>not-a-date</value></transactionDate>",
    )
    rows_bad = parse_form4(xml_bad)
    assert all(r["transaction_date"] != "not-a-date" for r in rows_bad)
    assert len(rows_bad) == 1  # only the S row survives
