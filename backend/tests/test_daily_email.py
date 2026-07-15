"""Offline tests for the daily email (Step 14)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.notify.daily_email import render_email, send_batch, unsubscribe_sig

client = TestClient(app)

PICKS = [
    {"rank": 1, "ticker": "SNDK", "name": "Sandisk", "alpha_score": 5.24,
     "predicted_return_30d": 0.028},
    {"rank": 2, "ticker": "AXON", "name": "Axon Enterprise",
     "alpha_score": 1.25, "predicted_return_30d": 0.0116},
]


def test_render_contains_data_and_disclaimer():
    subject, html = render_email("2026-07-14", PICKS, "http://api")
    assert "2026-07-14" in subject
    assert "SNDK" in html and "AXON" in html
    assert "+5.24" in html and "+2.8%" in html
    assert "not financial advice" in html.lower()
    assert "__UNSUB__" in html  # placeholder present for personalization


def test_send_batch_dry_run_without_key(monkeypatch, capsys):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    _, html = render_email("2026-07-14", PICKS, "http://api")
    result = send_batch(["a@x.com", "b@y.com"], "s", html, "http://api")
    assert result == {"sent": 2, "failed": 0, "dry_run": True}
    assert "[dry-run]" in capsys.readouterr().out


def test_unsubscribe_sig_deterministic_and_email_bound(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k1")
    a1, a2 = unsubscribe_sig("a@x.com"), unsubscribe_sig("a@x.com")
    b = unsubscribe_sig("b@y.com")
    assert a1 == a2 and a1 != b


def test_unsubscribe_endpoint(monkeypatch):
    import app.api.subscribe as sub_mod
    removed = {}
    monkeypatch.setattr(sub_mod, "remove_subscriber",
                        lambda email: removed.update(email=email))
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k1")
    sig = unsubscribe_sig("a@x.com")
    r = client.get(f"/api/unsubscribe?email=a@x.com&sig={sig}")
    assert r.status_code == 200 and removed["email"] == "a@x.com"
    assert client.get("/api/unsubscribe?email=a@x.com&sig=WRONG").status_code == 403


def test_winsorized_predicted_return_rank_invariant():
    import pandas as pd
    from app.ml.predict import ALPHA_CLIP

    alpha = pd.Series({"sndk": 5.24, "axon": 1.25})
    clipped = alpha.clip(-ALPHA_CLIP, ALPHA_CLIP)
    assert clipped["sndk"] == 3.0 and clipped["axon"] == 1.25
    assert list(alpha.rank()) == list(clipped.rank())  # ranking unchanged
