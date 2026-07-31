# Pre-registration — signal-card issue threshold (spec D1)

**Status:** REGISTERED 2026-07-22, decision pending measurement.
**Changes if adopted:** spec `docs/SIGNAL_PHASE_SPEC.md` D1 (which cards get
issued). Does NOT change scoring (settled 2026-07-22: plain z stays, see
`ROBUST_Z_PREREG.md`) and does NOT change resolution (D3) or the honesty
rules (D4).

## The problem this addresses

D1 issues a card when |alpha| >= 1.0. Because alpha is a plain z-score, the
threshold's meaning moves with the cross-section's extremity:

- measured 2026-07-22: mean 13.7 names/day cross +/-1.0 on the champion,
  but **27.9 (+105%) after deleting the single most extreme name**.
- same day, same threshold, 12 champion cards vs 54 on the 63d stream —
  because momentum_6_1's distribution isn't compressed by one outlier.

So the count of recommendations the product makes is partly a function of
how extreme its most extreme name happens to be. That is not a property
anyone would choose deliberately.

## Candidate schemes

- **T-FIXED (incumbent):** |alpha| >= 1.0.
- **T-QUANTILE:** top k% and bottom k% of the cross-section, k registered
  as **5** (≈25 names per side of ~503). Count is constant by construction;
  conviction varies (on a flat day the 5th percentile may be |alpha| 0.4).
- **T-HYBRID:** T-QUANTILE **intersected with** a conviction floor
  |alpha| >= 0.5 — constant-ish count on normal days, automatically fewer
  cards when the cross-section genuinely has little dispersion.

## Pre-registered decision rule (fixed BEFORE measurement)

Measured by `scripts/simulate_card_thresholds.py` over the full stored
factor history, per scheme, per stream (21d champion, 63d mom61):

1. **Count stability (the reason we are here):** mean |Δ count| when the
   single most extreme name is deleted and the cross-section re-thresholded
   must be **< 10%** (incumbent is 105%).
2. **Conviction retention:** the mean |alpha| of issued cards must be
   **>= 70% of T-FIXED's** mean |alpha| on the same dates. A scheme that
   issues many weak cards to stabilise the count is not an improvement.
3. **Usable band:** mean cards/day per stream in **[5, 40]**. Below 5 the
   product has nothing to show; above 40 it is a ranking with extra steps
   (and the display cap would be doing the real selection, invisibly).
4. If more than one scheme satisfies 1-3, pick the one with the higher
   conviction retention. If none does, **T-FIXED stays** and the
   methodology page states plainly that card counts vary with cross-
   sectional extremity.

**Explicitly not a criterion:** "issues more cards". More recommendations
is a business preference, not evidence.

## If a challenger wins

- D1 is amended (spec version bump) with the winning scheme and its k /
  floor constants written down.
- **Cards already issued are never re-issued, re-scored, or deleted**
  (append-only, D4). The change applies to new issues from a stated date,
  and `signal_cards` gains an `issue_rule` tag so the ledger can be split
  by rule when reporting hit rates — pooling cards issued under different
  selection rules would be the same error as pooling horizons (D7).
- Hit-rate cells collect from zero for the new rule; the pre-registered
  null bars (Appendix A) are re-derived if the issued population changes
  materially, because the null depends on the envelope, not the selection
  — but the *composition* of names changes, so the calibration is re-run
  and re-locked before any new claim.

## Honest expectation (recorded before measurement)

T-FIXED will fail rule 1 (already known: 105%). T-QUANTILE will pass 1 and
3 by construction and is the one at risk on rule 2. T-HYBRID is expected to
pass 1 and 2 and is at mild risk on rule 3 in quiet regimes. Predicting
T-HYBRID wins — recorded so the prediction can be graded like the last one
(which was wrong).


---

## Outcome (measured 2026-07-22, 120 dates, decision CLOSED)

    === momentum_composite (champion, 21d) ===
    T-FIXED (live)   19.7/day   Δ 6.5%   mean|α| 2.18   100%   ok/ok/ok
    T-QUANTILE 5%    52.0/day   Δ 2.8%   mean|α| 1.25    57%   ok/FAIL/FAIL
    T-HYBRID         50.8/day   Δ 3.1%   mean|α| 1.26    58%   ok/FAIL/FAIL

    === momentum_6_1 (position, 63d) ===
    T-FIXED (live)   58.9/day   Δ 2.1%   mean|α| 2.09   100%   ok/ok/FAIL
    T-QUANTILE 5%    51.0/day   Δ 2.0%   mean|α| 2.02    97%   ok/ok/FAIL
    T-HYBRID         51.0/day   Δ 2.0%   mean|α| 2.02    97%   ok/ok/FAIL

**DECISION: T-FIXED stays**, on both streams. On the champion it passes all
three rules outright; the challengers stabilise a count that was not
actually unstable, and pay 43% of the issued set's conviction to do it.
On the 63d stream no scheme satisfies rule 3, so rule 4 applies.

### Correction to this registration's premise (important)

The motivating figure — "+105% count change when the most extreme name is
deleted" — was measured by `compare_scoring_schemes.py` on the RAW
`momentum_12_1` column over 20 recent (SNDK-dominated) dates. **D1 does not
threshold on that column.** It thresholds on `momentum_composite`, where
the same metric over 120 dates is **6.5%** — inside the registered 10% bar.
The instability that triggered this registration is largely an artefact of
measuring the wrong object over a short, unusual window. Recorded rather
than quietly dropped: the registration produced a measurement that
overturned the claim that motivated it, which is the point of registering.

### What the data actually explains (the 12-vs-54 asymmetry)

`momentum_composite` is a weighted average of three imperfectly correlated
z-scores and is **never re-standardised**, so its own cross-sectional sigma
is ~0.5. A ±1.0 gate on it is therefore effectively a ±2 sigma gate, while
±1.0 on the single-signal `momentum_6_1` (sigma = 1 by construction) is a
much weaker gate. Same constant, different strictness — a SCALE artefact,
not an outlier effect. Evidence: 19.7/503 = 3.9% of names cross on the
champion vs 58.9/503 = 11.7% on the 63d stream.

### Open items created by this decision

1. **63d stream exceeds the usable band** (58.9/day vs 5-40). Not fixed
   here: no registered scheme qualifies. Presentation is already honest
   (display cap shows the top 24 by conviction and says so; all issued
   cards resolve and count). A stream-specific threshold requires its own
   registration.
2. **Composite standardisation** is the natural follow-up and is a much
   lighter decision than it sounds: dividing the composite by its own
   cross-sectional sigma each date is **rank-invariant** — no change to the
   ranking, the book, the IC, or any gate result. It changes only the
   DISPLAYED alpha scale and, through D1, the card counts. Because it
   touches displayed numbers and issuance it still gets a registration,
   but it needs no IC re-measurement.

### Rule 4 obligation discharged

Rule 4 requires that, when T-FIXED stays, "the methodology page states
plainly that card counts vary with cross-sectional extremity". Shipped
2026-07-22 in the site methodology section.
