"""API tests (Step 9) — TestClient + monkeypatched data access, no DB."""

import pytest
from fastapi.testclient import TestClient

import app.api.factors as factors_mod
import app.api.picks as picks_mod
import app.api.subscribe as subscribe_mod
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_picks_happy_path(monkeypatch):
    monkeypatch.setattr(picks_mod, "fetch_latest_prediction_date",
                        lambda mv: "2026-07-08")
    monkeypatch.setattr(picks_mod, "fetch_previous_factor_date",
                        lambda before: None)  # no prior day -> rank_change None
    monkeypatch.setattr(picks_mod, "fetch_predictions", lambda d, mv, n: [
        {"company_id": "id-1", "alpha_score": 2.1, "confidence": 0.97,
         "predicted_return_30d": 0.019, "position_size": 0.02},
        {"company_id": "id-2", "alpha_score": 1.8, "confidence": 0.93,
         "predicted_return_30d": 0.017, "position_size": 0.02},
    ])
    monkeypatch.setattr(picks_mod, "fetch_companies", lambda ids: {
        "id-1": {"id": "id-1", "ticker": "AAPL", "name": "Apple",
                 "sector": "IT"},
        "id-2": {"id": "id-2", "ticker": "MSFT", "name": "Microsoft",
                 "sector": "IT"},
    })
    r = client.get("/api/picks?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-07-08"
    assert body["count"] == 2
    assert body["picks"][0]["ticker"] == "AAPL"
    assert body["picks"][0]["rank"] == 1
    assert "not financial advice" in body["disclaimer"]


def test_picks_404_when_empty(monkeypatch):
    monkeypatch.setattr(picks_mod, "fetch_latest_prediction_date",
                        lambda mv: None)
    assert client.get("/api/picks").status_code == 404


def test_factors_happy_and_unknown(monkeypatch):
    monkeypatch.setattr(factors_mod, "fetch_company_by_ticker",
                        lambda t: {"id": "id-1", "ticker": "AAPL",
                                   "name": "Apple", "sector": "IT"}
                        if t.upper() == "AAPL" else None)
    monkeypatch.setattr(factors_mod, "fetch_factor_row", lambda cid, d: {
        "date": "2026-07-08", "momentum_composite": 1.2,
        "valuation_composite": None, "quality_composite": 0.3,
        "insider_congress_composite": 0.1,
    })
    r = client.get("/api/factors/aapl")  # case-insensitive
    assert r.status_code == 200
    assert r.json()["momentum_composite"] == 1.2
    assert client.get("/api/factors/ZZZZ").status_code == 404


def test_subscribe_validates_email(monkeypatch):
    captured = {}
    monkeypatch.setattr(subscribe_mod, "upsert_subscriber",
                        lambda email, source: captured.update(email=email))
    r = client.post("/api/subscribe", json={"email": "ismail@example.com"})
    assert r.status_code == 201
    assert captured["email"] == "ismail@example.com"
    assert client.post("/api/subscribe",
                       json={"email": "not-an-email"}).status_code == 422


def test_stats(monkeypatch):
    monkeypatch.setattr(subscribe_mod, "fetch_stats", lambda: {
        "companies_in_universe": 503,
        "latest_price_date": "2026-07-08",
        "latest_prediction_date": "2026-07-08",
        "model_versions": ["champion-momentum-v1", "lgbm-v1"],
    })
    r = client.get("/api/stats")
    assert r.status_code == 200
    assert r.json()["companies_in_universe"] == 503


def test_thesis_endpoint(monkeypatch):
    import app.api.theses as theses_mod
    monkeypatch.setattr(theses_mod, "fetch_company_by_ticker",
                        lambda t: {"id": "id-1", "ticker": "CIEN",
                                   "name": "Ciena", "sector": "IT"}
                        if t.upper() == "CIEN" else None)
    monkeypatch.setattr(theses_mod, "fetch_latest_thesis", lambda cid: {
        "date": "2026-07-08", "thesis_text": "Signal... Not financial advice.",
        "model": "claude-sonnet-4-6",
    })
    r = client.get("/api/thesis/cien")
    assert r.status_code == 200
    assert r.json()["thesis_text"].endswith("Not financial advice.")
    assert client.get("/api/thesis/ZZZZ").status_code == 404


def test_rankings_search_and_pagination(monkeypatch):
    import app.api.rankings as rankings_mod
    import app.api.picks as picks_mod2
    monkeypatch.setattr(picks_mod2, "fetch_latest_prediction_date",
                        lambda mv: "2026-07-08")
    monkeypatch.setattr(rankings_mod, "fetch_all_predictions",
                        lambda d, mv: [
        {"company_id": f"id-{i}", "alpha_score": 5.0 - i,
         "predicted_return_30d": 0.01} for i in range(5)
    ])
    monkeypatch.setattr(picks_mod2, "fetch_companies", lambda ids: {
        f"id-{i}": {"id": f"id-{i}",
                    "ticker": ["SNDK", "AXON", "CIEN", "LITE", "FICO"][i],
                    "name": ["Sandisk", "Axon", "Ciena", "Lumentum", "Fair Isaac"][i],
                    "sector": "IT"} for i in range(5)
    })
    r = client.get("/api/rankings?offset=1&limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert [row["ticker"] for row in body["rows"]] == ["AXON", "CIEN"]
    assert body["rows"][0]["rank"] == 2  # global rank preserved under pagination

    r2 = client.get("/api/rankings?search=cien")
    assert [row["ticker"] for row in r2.json()["rows"]] == ["CIEN"]
    r3 = client.get("/api/rankings?search=fair")   # name search too
    assert [row["ticker"] for row in r3.json()["rows"]] == ["FICO"]


def test_sparklines_endpoint(monkeypatch):
    import app.api.rankings as rankings_mod
    monkeypatch.setattr(rankings_mod, "fetch_sparklines",
                        lambda tickers, days: {"SNDK": [10.0, 11.0, 12.5]})
    r = client.get("/api/sparklines?tickers=sndk,axon&days=90")
    assert r.status_code == 200
    assert r.json()["series"]["SNDK"] == [10.0, 11.0, 12.5]
    assert client.get("/api/sparklines?tickers=").status_code == 422


def test_performance_endpoint(monkeypatch):
    import app.api.rankings as rankings_mod
    rows = [
        {"date": "2026-07-01", "strategy_return": 0.01,
         "benchmark_return": 0.005, "strategy_equity": 1.01,
         "benchmark_equity": 1.005},
        {"date": "2026-07-02", "strategy_return": -0.002,
         "benchmark_return": 0.001, "strategy_equity": 1.008,
         "benchmark_equity": 1.006},
    ]
    monkeypatch.setattr(rankings_mod, "fetch_performance", lambda: rows)
    r = client.get("/api/performance")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 2
    assert body["sharpe"] is not None
    assert "Backtested" in body["note"]

    monkeypatch.setattr(rankings_mod, "fetch_performance", lambda: [])
    assert client.get("/api/performance").status_code == 404


def test_picks_rank_change(monkeypatch):
    monkeypatch.setattr(picks_mod, "fetch_latest_prediction_date",
                        lambda mv: "2026-07-08")
    monkeypatch.setattr(picks_mod, "fetch_predictions", lambda d, mv, n: [
        {"company_id": "id-1", "alpha_score": 2.1, "confidence": 0.97,
         "predicted_return_30d": 0.019, "position_size": 0.02},
    ])
    monkeypatch.setattr(picks_mod, "fetch_companies", lambda ids: {
        "id-1": {"id": "id-1", "ticker": "AAPL", "name": "Apple",
                 "sector": "IT"}})
    monkeypatch.setattr(picks_mod, "fetch_previous_factor_date",
                        lambda before: "2026-07-07")
    monkeypatch.setattr(picks_mod, "fetch_momentum_ranks",
                        lambda d: {"id-1": 1} if d == "2026-07-08"
                        else {"id-1": 4})
    r = client.get("/api/picks?limit=1")
    assert r.status_code == 200
    assert r.json()["picks"][0]["rank_change"] == 3  # climbed 4 -> 1
