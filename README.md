# Institutional AI Stock Prediction Engine

3-month MVP: ranks ~500–1000 US stocks daily with a confidence-weighted alpha
score built from 3 active factors (of a 17-factor scaffolded architecture),
100% open-source data, LLM-generated investment theses.

**Spec:** `institutional_ai_stock_prediction_factor_spec.md` is the single
source of truth. **AI sessions:** read `CLAUDE.md` first.

## The 3 active MVP factors

| # | Factor | Data source |
|---|--------|-------------|
| 1 | Momentum / Technical (12-1, RSI, MACD) | yfinance OHLCV |
| 2 | Valuation — Value + Quality composite | yfinance fundamentals |
| 3 | Insider + Congressional trading | SEC EDGAR Form 4 + House/Senate disclosures |

The other 14 factor groups are scaffolded (registry entries + directories +
`NotImplementedError` compute), activated in Phases 6–7.

## Stack

Python 3.11+ · FastAPI · LightGBM · Supabase (Postgres) · Next.js 14 ·
Railway · Vercel · Anthropic API. Do not swap components — see spec §Tech Stack.

## Quickstart (backend)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # fill in keys
python -c "import yfinance, lightgbm, fastapi, supabase, anthropic, ta; print('ok')"
```

## Layout

```
backend/app/factors/   17 factor groups (3 active, 14 scaffolded)
backend/app/{api,ml,backtest,data_pipeline,llm,utils}
backend/tests/         unit + fixtures/ + integration/
database/              SQL migrations (001_initial_schema.sql)
frontend/              Next.js 14 (initialized in Step 11)
notebooks/             research & backtest R&D
data/, reports/        gitignored caches and outputs
```

## Status

Phase 0 (Week 1) in progress. See ledger in `CLAUDE.md`.

**Disclaimer:** Backtested. Not financial advice. Past performance does not
guarantee future results.
