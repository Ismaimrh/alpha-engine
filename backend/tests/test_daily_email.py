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


def test_force_dry_beats_present_key(monkeypatch, capsys):
    """Regression: --dry-run sent a real email because load_dotenv restored
    the popped key. force_dry must win over an existing key."""
    monkeypatch.setenv("RESEND_API_KEY", "real-key")
    _, html = render_email("2026-07-14", PICKS, "http://api")
    result = send_batch(["a@x.com"], "s", html, "http://api", force_dry=True)
    assert result["dry_run"] is True and result["sent"] == 1
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


def test_email_renders_signal_cards_section():
    cards = [{"ticker": "SNDK", "direction": "BUY", "entry": 100.0,
              "target": 118.5, "stop": 91.2, "horizon_days": 21},
             {"ticker": "XYZ", "direction": "AVOID", "entry": 50.0,
              "target": 55.0, "stop": 47.0, "horizon_days": 63}]
    _, html = render_email("2026-07-17", PICKS, "http://api", cards=cards)
    assert "NEW SIGNAL CARDS" in html
    assert "target 118.50" in html and "stop 91.20" in html
    assert "SWING · 21d" in html and "POSITION · 63d" in html  # split labels
    assert "not a short" in html
    _, html2 = render_email("2026-07-17", PICKS, "http://api", cards=[])
    assert "NEW SIGNAL CARDS" not in html2
