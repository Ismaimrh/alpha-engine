# Signal Phase Spec (v1) — from ranking service to signal service

**Status:** DRAFT — awaiting human approval before any code.
**Date:** 2026-07-18. **Origin:** external review strategic appendix (2026-07-18),
adapted; decisions below are OURS and pre-registered here.
**Prime directive (from the review itself, which we endorse):** make momentum a
great *product* before expanding factors. No new factor work inside this phase.

---

## 1. The pivot, stated precisely

- Current unit of value: a **rank** ("SNDK is #1, alpha +5.17").
- New unit of value: a **SignalCard** — a specific, time-bounded, resolvable
  recommendation: direction, entry, target, stop, horizon, confidence,
  trigger reason — issued, tracked in a ledger, and publicly scored.

The ranking product stays; SignalCards are a layer on top of the SAME champion
signal. No methodology change, no new model.

## 2. Pre-registered design decisions

### D1 — Direction mapping (from champion alpha, 21d horizon)
- BUY:   alpha_score >= +1.0 (top ~15% of the cross-section, empirically)
- AVOID: alpha_score <= -1.0
- HOLD:  everything else (not issued as cards; visible in rankings only)
Rationale: cards must be selective; issuing 503 cards daily is a ranking with
extra steps.

### D2 — Trade envelope (vol-scaled, NOT fixed percentages)
Let sigma_21 = realized 63d daily vol * sqrt(21) (already computed for low_vol).
- entry  = latest close at issue
- target = entry * (1 + 1.5 * sigma_21)
- stop   = entry * (1 - 1.0 * sigma_21)
- expected_hold_days = 21 trading days; expires_at = issue + 21 trading days
Rationale: fixed +/-10%/5% envelopes ignore that SNDK's monthly sigma is ~4x
JNJ's. Vol-scaling makes hit rates comparable across names. The 1.5/1.0
asymmetry encodes the positive expected drift of a BUY signal; these constants
are pre-registered and may only change with a new spec version.

### D3 — Resolution rule (close-touch approximation, documented)
A card resolves at the FIRST of: (a) daily close >= target -> HIT,
(b) daily close <= stop -> STOP, (c) expiry -> EXPIRED (return recorded,
counts as neither hit nor stop in hit-rate; shown separately).
LIMITATION, stated on the product: resolution uses daily CLOSES, not intraday
highs/lows — a stop pierced intraday but recovered by close does not trigger.
(If price_features stores high/low, upgrade to intraday-touch in S2 with a
spec amendment; do not silently switch.)

### D4 — Honesty rules for displayed accuracy (non-negotiable)
- Hit rate is ALWAYS shown as: value + Wilson 95% CI + N resolved.
- No hit-rate is displayed until N >= 30 resolved cards ("collecting" state).
- EXPIRED cards are excluded from hit-rate but shown in the ledger with their
  realized return — no survivorship pruning, ever.
- The ledger is public and append-only (cards are never deleted or edited
  after issue; corrections happen via new rows).

### D5 — What we are NOT doing in this phase (rejected/deferred from review)
- Multi-horizon (5d/63d) streams: S2, after the 21d card loop is proven.
- Russell 3000, intraday data, options flow, push notifications: deferred.
- Event-driven triggers (earnings/news/revisions): S3 candidate, own spec.
- Regime detector: S3 candidate.

## 3. Build plan (S1) — gated

- S1.1 Migration 013: `signal_cards` table (issue fields + resolution fields,
  unique(ticker, issue_date, horizon, model_version), append-only by policy).
- S1.2 `app/signals/cards.py`: pure card construction from the champion
  cross-section + vol inputs (D1/D2), offline-tested.
- S1.3 Issue step wired into nightly (after predictions): issues BUY/AVOID
  cards for the day; idempotent.
- S1.4 `app/signals/resolve.py`: nightly resolver applying D3 against the
  close panel; idempotent, mirrors prediction_outcomes discipline.
- S1.5 API: `GET /api/signals` (open cards), `GET /api/signals/ledger`
  (resolved, paginated), `GET /api/hitrate` (D4 shape).
- S1.6 Frontend: "Signals" tab — open SignalCards (entry/target/stop drawn on
  the sparkline), hit-rate header in D4 state, ledger view.
- S1.7 Email: daily email gains the day's new cards (same envelope fields).

**GATE S1 (before any public accuracy claim):**
1. >= 20 issued cards resolved, and every resolution independently
   reproducible from price_features (spot-check script provided).
2. Hit-rate endpoint returns D4-compliant shape (CI + N) and the UI renders
   the "collecting" state correctly below N=30.
3. Ledger append-only verified (no UPDATE path exists in code).

**Timeline honesty:** first cards issue the night after deploy; first
resolutions ~21 trading days later (~late Aug if deployed now); Gate S1
verdict ~mid-September — conveniently aligned with Gate 4.

## 4. Success criterion for the phase (pre-registered)
The phase succeeds if, by Gate S1 + 30 resolved cards:
- the close-touch hit rate's Wilson CI lower bound is > 40% with the 1.5/1.0
  envelope (a coin-flip direction with this asymmetric envelope yields ~35-40%
  hits; we need to beat the envelope's own geometry, not 50%), AND
- the machinery ran unattended (no manual interventions in the ledger).
If it fails: we keep the ranking product, publish the failed hit rate anyway
(D4), and diagnose before S2. Deleting the Signals tab quietly is not an option.

---

# Amendment v1.1 — S2: the 63-day "position card" stream (DRAFT, awaiting approval)

**Date:** 2026-07-19. **Trigger:** research batch 3 finding — momentum_6_1 is
dead at 21d (t=0.19) but the strongest 63d signal measured (IC 0.0567,
t=7.03, ICIR 0.372, hit 65.6% over 358 days). Medium-horizon momentum
predicts the quarter. This amendment productizes that finding without
touching anything S1 registered.

## D6 — The 63d stream, pre-registered
- Signal: momentum_6_1 z-score (as measured in the batch-3 gate; no
  reweighting, no blending — the thing that passed is the thing that ships).
- Model version: `cand-mom61-63d-v1`, written nightly as a 4th tracked
  prediction stream. Its predicted return is calibrated on 63d forward
  excess returns (its own horizon — NOT the 21d slope), same in-sample
  labeling and ±3σ display cap as all streams.
- Cards: direction thresholds ±1.0 (same as D1, same compression caveat);
  envelope scaled to the horizon: sigma_63 = daily_vol * sqrt(63),
  target = entry * (1 + 1.5 * sigma_63), stop = entry * (1 - 1.0 * sigma_63),
  hold = 63 trading days. Close-touch resolution (D3) unchanged.
- Labeling: UI and email must mark these visually as "POSITION · 63d" —
  a quarterly card sold as a monthly card would be a lie of omission.

## D7 — Horizon separation (non-negotiable)
- Hit rates are reported PER HORIZON, never pooled. A 21d book and a 63d
  book have different envelope geometry; pooling would let one subsidize
  the other's optics. /api/hitrate gains a horizon dimension; each obeys
  its own N>=30 collecting rule.
- prediction_outcomes resolution becomes horizon-aware via an explicit
  HORIZON_BY_MODEL map (the table's key already carries horizon_days —
  designed for this in S1.1). 21d streams keep resolving exactly as today.

## D8 — Explicitly NOT in S2
- Intraday-touch resolution upgrade: DEFERRED to S3. Changing the
  resolution rule mid-collection would break comparability of the 21d
  ledger already accruing. When it happens, it happens for new cards only,
  under its own amendment.
- 5d horizon, new signals, robust-z rescoring: separate decisions.

## Gate S2 (before any public 63d accuracy claim)
1. 63d stream's realized ICs accrue in prediction_outcomes at horizon=63
   and reconcile with the gate-2 estimate's sign.
2. 63d hit rate obeys its own collecting state (N>=30; first resolutions
   ~3 calendar months post-deploy — honesty: this gate cannot pass before
   ~November 2026).
3. 21d ledger demonstrably unaffected (same counts before/after deploy).

## Success criterion
Wilson CI lower bound of the 63d close-touch hit rate > 40% at N>=30, with
unattended operation — same bar structure as S1, judged independently.

---

# Amendment v1.2 — external-review dispositions (2026-07-19)

Review of v1/v1.1 received post-S1-deploy. Dispositions (ledger of record):

1. **Success bar re-derivation — ACCEPTED, method (b).** The 40% bar came
   from an arithmetic-barrier argument; log-barriers imply ~44-47%; BOTH
   are wrong for discrete close-touch with expiry exclusion. The bar is now
   defined as: **empirical null hit rate + 5pp, per direction and horizon**,
   where the null is measured by `scripts/calibrate_null_hitrate.py` —
   random-direction cards through the REAL resolver over the REAL panel.
   The measured numbers are locked into the appendix below once run.
   Sandbox validation on synthetic drifting paths: BUY null ~41%, AVOID
   null ~22% — which mandates the per-direction split (see 2).
2. **AVOID cards (G1) — mechanics were already mirrored** (resolver hits on
   falls; tested). Accepted the PRODUCT critique: UI displayed BUY-frame
   prices. Fixed: mirrored display levels, "avoid / underweight — not a
   short recommendation" label, and hit rates now reported PER DIRECTION
   (BUY and AVOID nulls differ ~2x; pooling would launder noise).
   Ledger rows unchanged (append-only holds).
3. **Entry vs fill (G2) — ACCEPTED (a):** footnote on cards and email:
   entry = issue close; next-day fills differ; overnight gap risk is the
   reader's. Phantom-hit limitation folded into the same disclosure.
4. **Position sizing (G3) — option (c), diverging from review's (a):**
   cards carry NO size; printed sizes imply false precision. Methodology
   states backtests assume equal-weight top-N; users size themselves.
5. **Delisting (G4) — ACCEPTED:** D3 gains case (d): a terminated series
   (no prints >5 trading days while the panel advances) resolves at last
   available close — touch events on the available path still win first
   (bankruptcy slides hit stops; M&A pops hit targets). Tested.
6. **Ledger fence (G5) — ACCEPTED:** `scripts/ledger_hash.py` row-level
   SHA256; S2 Gate #3 now reads "digest identical modulo appended rows".
7. **as_of_date (S1.1) — REJECTED as already-correct:** issue_date IS the
   trading date of the underlying prediction (not wall-clock); re-runs
   upsert the same key. Documented here instead of renamed.
8. **Email paradigm mixing — REJECTED as not-the-case:** cards render as a
   separate section, not mixed into the picks table.
9. **"Manual intervention" (§4) — DEFINED:** allowed: infra restarts,
   re-running idempotent nightly steps, full-panel price backfills, schema
   ADDITIONS. Criterion-voiding: any UPDATE/DELETE on signal_cards outside
   the resolver's single status transition, changing D1/D2 constants
   mid-collection, or manual edits to resolution fields.

Roadmap items from the review (streak line, 5d stream, event triggers,
multi-card grouping, backtested "what-would-have-been" page clearly labeled
BACKTESTED) are acknowledged and parked in the backlog, not this phase.

## Appendix A — null hit-rate calibration (MEASURED 2026-07-19, LOCKED)
Panel 547 dates x 503 names, 10,000 null cards per horizon, seed 42,
random-direction cards through the production resolver:

    21d  BUY   null 0.3721  (631 hit / 1065 stop / 3229 expired)
    21d  AVOID null 0.2630  (515 hit / 1443 stop / 3117 expired)
    63d  BUY   null 0.4099  (878 hit / 1264 stop / 2818 expired)
    63d  AVOID null 0.2303  (507 hit / 1694 stop / 2839 expired)

Notes: ~65% of null cards EXPIRE (discrete close-touch barriers are hard
to reach) — both the original 40% arithmetic estimate and the review's
44-47% GBM estimate were wrong; measurement was the only defensible path.

**PRE-REGISTERED SUCCESS BARS (null + 5pp), per direction and horizon:**

    21d BUY 42.2% | 21d AVOID 31.3% | 63d BUY 46.0% | 63d AVOID 28.0%

Wilson CI lower bound must exceed the bar at N>=30 per cell. Ledger
before-digest for Gate S2 #3: 4caf9ed68b69da2f8e8e7c2a7a3809e0
8077085b806dd8ebc352229643745029 (5 rows, 0 resolved, 2026-07-19).
S2 (v1.1) status: **APPROVED** with these bars.
