# CLAUDE.md — House Rules for AI-Pair-Programming Sessions

Single source of truth: `institutional_ai_stock_prediction_factor_spec.md` (v3)
plus the amendments listed below. Read it fully before acting.

## Non-negotiable rules

1. **Follow the 14-step build plan in strict order.** After each step: build,
   run the spec's verification command, report, and WAIT for the human to say
   "continue". Never skip ahead. Never start a phase early.
2. **Do not change the tech stack.** FastAPI, LightGBM, Supabase, Next.js,
   Railway, Vercel, yfinance, SEC EDGAR, `ta`, Anthropic API. If a task seems
   to need a new tool, push back and ask the human first.
3. **Stop-and-Validate Gates are hard stops.** Gate 1 (data quality, Wk 2),
   Gate 2 (factor IC, Wk 4), Gate 3 (Sharpe > 1.0, Wk 6), Gate 4 (paper
   trading, Wk 8), Gate 5 (users, Wk 12). If a gate fails, fix — do not stack.
4. **No look-ahead bias.** Point-in-time discipline everywhere. Purge gaps in
   walk-forward. Never report backtest results without transaction costs.
5. **Ambiguity → ask the human.** Do not invent requirements.
6. **No stub files for future steps.** Directories may exist with `.gitkeep`;
   a `.py` file is only created in the step that implements it. An empty file
   claiming to be a module misleads future sessions.

## Structure amendments (v3.1, agreed with the human)

- Added: `notebooks/`, `data/` (gitignored), `reports/` (gitignored),
  `backend/tests/fixtures/`, `backend/tests/integration/`, this `CLAUDE.md`.
- Deferred to their build steps: `Dockerfile` (Step 12), `infra/*` (Step 12),
  `.github/workflows/*` (Phase 0 task 6, after code exists), `docs/*` content.
- Rejected: `core/` rename of `utils/` (spec names `utils/`), dedicated
  `observability/` module (MVP uses Sentry + UptimeRobot + `system_logs`).
- Dependencies: pinned to latest stable resolved set as of 2026-07-08, not the
  spec's stale pins (human decision — yfinance 0.2.40 was a pipeline-breakage
  risk). Pins live in `backend/requirements.txt`; keep them pinned.


## Decision record (v3.1 continued)

- 2026-07-08 — US-only MVP universe (S&P 500) confirmed by human; Europe
  (Euronext/STOXX) deferred to Phase 6. System made multi-region-ready:
  migration 002 (region/exchange/currency), get_universe(region=...),
  normalize_us_ticker scoped to US sources (EU tickers keep dot suffixes).
  ETFs out of scope for factor ranking; revisit after Gate 3.
- 2026-07-08 — Schema gaps found & fixed via migrations: 003 eps_std_3y
  (quality composite needs it), 004 insider dedup key (accession+row_seq),
  005 congress dedup key (content hash). Spec schema had no unique keys on
  transaction tables.
- 2026-07-08 — INCIDENT: sandbox filesystem rollback ate Step 5.1-5.3 files
  mid-session; restored byte-identically from conversation history. The
  human's local copy (which ran the backfills) was never affected and is
  the source of truth. Lesson: commit each step zip to git immediately.

- 2026-07-09 — Congress Plan A DEAD: both Stock Watcher S3 mirrors return
  403 (verified by human). Plan B adopted: direct Senate EFD loader
  (efdsearch.senate.gov, official source; electronic PTRs only, paper
  filings counted+skipped). House PTRs are PDFs -> DEFERRED post-MVP;
  composite runs senate-only insider+senate legs. congress_loader's
  normalize/dedup/upsert path reused unchanged (source='senate_efd').

## Project status ledger (update at every step)

- [x] Step 1 — Repo and dependencies (done 2026-07-08; deps repinned to latest stable per v3.1)
- [x] Step 2 — Database (done 2026-07-08; 11 tables verified live by human via verify_db.py.
      Note: Supabase renamed keys — we use the sb_secret_ key in SUPABASE_SERVICE_KEY)
- [x] Step 3 — Universe loader (done 2026-07-08; 503 tickers seeded, verified by human)
- [x] Step 4 — Factor registry + 3 active factors + scaffolds (done 2026-07-08; 30 tests pass.
      Resolution: registry keyed by factor GROUP (17 entries = 16 factor dirs + LLM
      layer) because spec's per-signal example (21 entries) contradicts the
      binding assert len == 17)
- [x] Step 5 — Data pipelines (5.1 prices 503/503 260k rows; 5.2 fundamentals 503/503;
      5.3 insider w/ checkpoint+resume, human launched full run; 5.4 congress run by human;
      migrations 001-005 applied)
- [x] GATE 1 — FULLY PASSED 2026-07-09 (15/15 green). Insider 98.2% coverage,
      54k rows; 1 PIT-violating row quarantined+deleted by human; congress live via
      Senate EFD. PTC tz-suffix date bug fixed + regression-tested. Pagination bug
      (offset paging without total order -> duplicate rows) fixed across all fetches.
      (Original conditional-pass note:) Green: prices 100%/fresh/0-null, fundamentals 100% (nulls 0.8-6.8%), PIT violations 0 everywhere.
      Exception A: insider coverage 7.6% = snapshot taken mid-backfill (transient); re-run gate after insider.log completes.
      Exception B: congress 0 rows AND no congress quality-log entries -> backfill_congress.py likely never completed on human machine; re-run + paste output. If sources dead -> Plan B (EFD/Clerk scraper). Factor degrades to insider-only meanwhile.
      HARD RULE: Gate 1 must be fully green before Gate 2 backtesting.
- [x] Step 6 — Compute factors (6.1 daily: 503 scored, 365 valuation-investable;
      6.2 history: 261,560 rows / 520 dates, human-verified. Original note:
      RUN ONLY AFTER insider backfill completes + gate green. Congress: RESOLVED via
      Senate EFD (662 rows, fresh 2026-07-08); insider coverage transient, backfill running)
- [ ] Step 6 — Compute factors
- [~] GATE 2 — PASSED 2026-07-10: momentum IC 0.0396 (t=5.39, hit 59.3%, spread
      +31.4% ann pre-cost) over 486 days. Insider FAILED (-0.0039, t=-0.93):
      sell-dominated tape + zero-inflation + horizon mismatch; watch-item, formula
      rework candidate, ensemble will weight empirically. Valuation: insufficient
      history (snapshot-only), excluded as documented.
- [x] GATE 3 — PASSED 2026-07-10: after-cost Sharpe 1.703 (benchmark 1.188),
      ann 41.8% vs 18.9%, maxDD -16.7% vs -17.9%, turnover 65.5%/rebal, cost drag
      1.13%/yr. Caveat on record: single friendly regime; Gate 4 = real OOS test.
- [x] Step 7 — Backtest (7.1 metrics: forward returns, Spearman IC, ICIR/t-stat,
      decile spreads; 7.2 walk-forward engine: monthly rebalance, top-N equal-weight,
      per-side bps costs on turnover, EW-universe benchmark, no-lookahead tested +
      gate3_backtest.py delivered. Awaiting human Gate 3 run)
- [~] Step 8 — ML ensemble (8.1 HUMAN-VERIFIED: ensemble OOS IC 0.0219 (t=4.42)
      vs momentum baseline 0.052 (t=6.41) on 356 OOS days, purge gaps 23d all folds.
      Lesson recorded: ~500 effective obs -> GBM overfits; importances != OOS value
      (dead insider got 27%). DECISION (a): champion/challenger. Champion =
      champion-momentum-v1 (user-facing); challenger = lgbm-v1 tracked for
      data-driven promotion. 8.2 code done (predict.py, migration 007, script).
      LLM role clarified: explanation layer + feature extraction, never the ranker
      (untestable: training data contains historical outcomes). (8.1 notes: excess-return target, purged
      walk-forward w/ verifiable fold gaps (21d+2d embargo), quarterly retrain,
      final-model + importances, train_ensemble.py eval script. Fixture bug in
      test world caught & fixed (drift misaligned with signal). Awaiting human
      run. Next: 8.2 daily predict -> predictions table)
- [x] Step 9 — API (HUMAN-VERIFIED: /health, /api/picks (top-10 face-valid:
      SNDK/AXON/CIEN/LITE momentum + healthcare defensives), /api/factors/NVDA OK.
      Pending cosmetic: winsorize alpha at prediction layer (SNDK 5.2σ outlier;
      rank-invariant so Gates 2/3 unaffected). (Code notes: main.py + /health (DB-free liveness), /api/picks
      (ticker-resolved, disclaimer), /api/factors/{ticker}, /api/subscribe
      (EmailStr), /api/stats; CORS via FRONTEND_ORIGIN; 6 TestClient tests with
      monkeypatched data access; ci.yml landed (deferred Phase 0 task). Awaiting
      human local uvicorn verification)
- [x] Step 10 — LLM theses (HUMAN-VERIFIED: 10 theses, $0.0533 total, quality
      review passed (data-faithful, real risk paragraph). FLAG OPEN: CIEN 12-1
      return 509% + SNDK 5.2σ — human to eyeball charts; possible yfinance
      adjustment artifact. Prompt backlog: magnitude calibration, ban markdown.
      (Code notes: prompts.py w/ anti-fabrication system prompt,
      ThesisGenerator (registry group 17 now resolves), migration 008 dedup,
      generate_theses.py w/ --max-cost budget guard + spend ledger in llm_theses.
      Model claude-sonnet-4-6; pricing constants flagged for verification.
      Awaiting human run w/ real API key)
- [~] Step 11.5 — Frontend v2 (human feedback: too minimal/limited; chose ALL 4
      features + dense terminal look; InvestWatcher blueprint adopted for
      disciplines (state completeness, React Query, Recharts) NOT auth/sidebar.
      Backend enablers DONE: /api/rankings (search+pagination), /api/sparklines
      (batch), /api/performance (precomputed via migration 009 +
      export_performance.py — human ran: 498 rows, Sharpe 1.703 reproduced),
      picks.rank_change. Frontend v2 DONE: React Query + Recharts, tabbed views
      (Top Picks w/ sparklines + rank deltas + expandable factor/thesis panels,
      Full Ranking w/ debounced search + pagination, Performance w/ equity chart
      + stats band), dense terminal on Alpha Engine identity, state completeness
      (skeleton/error/empty everywhere). Awaiting human npm install + visual check.
      (v1 notes: Next.js 14 App Router + Tailwind, hand-
      scaffolded (no node_modules shipped). Design: paper factor-sheet, Archivo/
      Inter/IBM Plex Mono, signature AlphaBar deviation bars clipped ±3σ.
      Components: PicksTable (expandable rows -> factors + thesis), SubscribeBox,
      status line. Backend gained GET /api/thesis/{ticker}. Awaiting human
      npm install + npm run dev)
- [~] Step 12 — Deploy (code done: nightly_update.py orchestrator (critical vs
      soft steps, tuned fractional-year windows), nightly.yml (Tue-Sat 01:30 UTC),
      weekly_congress.yml (headed Chrome under xvfb — solves EFD-on-CI),
      railway.json + Procfile, DEPLOY.md runbook (~$1-2/mo). Awaiting human:
      GitHub push, Railway, Vercel, secrets, manual workflow smoke tests)
- [ ] Step 13 — Paper trade
- [ ] Step 14 — Launch
