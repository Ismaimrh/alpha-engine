# Alpha Engine — an institutional-grade factor platform, run honestly

**Live:** daily S&P 500 factor rankings, signal cards with a public hit-rate
ledger, and LLM-written theses — rebuilt nightly by automation, operated for
~$2/month.

> Backtested signals, not financial advice.

## What this is

A quantitative equity research platform built solo in ~2 weeks with an AI
pair-programmer, then operated live. It ranks 503 names nightly on
cross-sectional factors, backs a champion model with two tracked rivals,
issues resolvable BUY/AVOID signal cards, explains its picks in plain English
via LLM, and emails subscribers — all on free-tier infrastructure.

The differentiator is not the model. It is the **process**: every claim the
system makes publicly is gated, pre-registered, and falsifiable.

## The numbers (and exactly what they mean)

| Metric | Value | Caveat — read it |
|---|---|---|
| Momentum factor IC (21d) | ~0.029, t≈4.0, 511 days | Walk-forward, cross-sectional Spearman; 0.029–0.040 across adjustment bases/windows |
| Sector-relative momentum IC | 0.032 / t=5.7 (21d); 0.039 / t=7.1 (63d) | Beats raw momentum on IC; book Sharpe is a wash — construction mediates |
| Champion backtest Sharpe (after 10bps/side) | 1.72 vs benchmark 1.25 | Single ~2-year regime; the live paper race is the real test |
| Live paper-trading verdict | **PENDING** | First realized outcomes ~Aug 2026; promotion needs 60 common days + paired-t p<0.05 |
| Signal-card hit rate | **COLLECTING** (0/30) | Displayed only at N≥30 with Wilson CI — pre-registered |

If a table like this ever shows only flattering numbers with no caveat
column, distrust it.

## Architecture

```
GitHub Actions (nightly cron + weekly headed-Chrome scraper)
        │  runs the same scripts a laptop runs
        ▼
   Supabase (Postgres) ── the only state in the system
        ▲                        ▲
        │ reads per request      │
   FastAPI on Railway ◄── Next.js on Vercel (terminal-dense UI)
        │
   Resend (daily email, signed one-click unsubscribe)
```

- **Data:** yfinance OHLCV (full-window nightly refetch — partial refreshes
  splice dividend-adjustment bases; we learned this the hard way, see
  incident below), SEC EDGAR Form 4 (54k insider rows, point-in-time by
  filing date), Senate eFD (Selenium under xvfb — the disclosure site blocks
  headless Chrome).
- **Factors:** 4 live composites + 8 tracked candidates, each a standalone
  column judged by pre-registered IC gates (≥0.02 mean, t≥2).
- **Models:** three prediction streams nightly — rules champion,
  sector-relative candidate, LightGBM challenger (purged walk-forward,
  21d+2d embargo). Promotion is decided ONLY on realized prediction ICs
  with a paired-t significance test. Backtests cannot promote anything.
- **Signals:** BUY/AVOID cards with vol-scaled envelopes
  (entry ±1.5σ/1.0σ), close-touch resolution, append-only public ledger.
- **LLM layer:** Claude writes per-stock theses from the factor table under
  an anti-fabrication prompt (numbers only from provided data); ~$0.005/thesis.

## Process highlights (the actual portfolio piece)

- **Stop-and-validate gates.** Data quality (Gate 1), factor IC (Gate 2),
  after-cost portfolio (Gate 3), live paper trading (Gate 4), launch
  checklist (Gate 5), signal-product accuracy (Gate S1). Failing a gate
  stops the build; three factor candidates died at Gate 2 and stayed dead.
- **Pre-registration.** Thresholds are written down before results exist.
  When insider-v2 scored IC 0.0181 against a 0.02 bar (t=6.4!), it was NOT
  promoted — it joined the ML ensemble's feature set instead, a venue whose
  admission rule (predictive content, sign-agnostic) was itself registered.
- **A reproducibility incident, kept.** Momentum IC moved 0.0396→0.0251
  between two "identical" runs. Root cause: nightly partial price refreshes
  spliced yfinance adjustment bases. Fix: full-window refetch + a panel
  sentinel that refuses to compute factors on a short panel. The incident
  and the sampling-range honesty (0.029–0.040) are documented, not buried.
- **Wrong-signed factors stay wrong-signed.** Short-term reversal and
  low-vol failed with t=−3 and t=−9. Flipping signs post-hoc is data
  snooping; the theses were rejected. (As features for a sign-agnostic GBM,
  they're admissible — and that distinction is written down too.)
- **Honest UI states.** The hit-rate header says "0/30 — collecting" rather
  than showing an early number. Model cards say "pending — first outcomes
  ~mid-Aug." The email discloses that expected returns are in-sample
  calibrated and capped.

## Run it

```bash
# backend
cd backend && python -m venv ../venv && ../venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill Supabase/Anthropic/SEC/Resend values
python -m pytest -q    # 164 offline tests, no network needed
# apply database/0*.sql to Supabase in order, then:
python scripts/backfill_prices.py && python scripts/backfill_factor_scores.py --restart
python scripts/nightly_update.py   # the whole nightly, manually

# frontend
cd frontend && npm install && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Deployment runbook: `DEPLOY.md`. Decision ledger (every gate verdict,
incident, and rejected idea): `CLAUDE.md`. Signal product spec:
`docs/SIGNAL_PHASE_SPEC.md`.

## Honest limitations

Single ~2-year bull-ish regime; snapshot-only fundamentals (valuation factor
awaiting history accrual); close-touch card resolution ignores intraday
touches; survivorship-lite universe (current S&P constituents); one
operator, prod == staging. Each is ledgered with its planned remedy.
