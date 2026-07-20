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
