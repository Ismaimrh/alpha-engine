# Pre-registration — momentum cross-sectional scoring scheme

**Status:** REGISTERED 2026-07-22, decision pending measurement.
**Why this needs pre-registration:** the momentum composite's scoring scheme
determines the LIVE ranking, the champion's book, and the ±1.0σ signal-card
threshold. Changing it after seeing which variant looks better would be
exactly the post-hoc selection this project refuses everywhere else.

## Motivation (the observation that triggered this)

2026-07-22, first dual-stream card issue: **12 cards from the champion
(21d, plain z on momentum_composite) vs 54 from the 63d stream** at the
IDENTICAL ±1.0σ threshold. Cause is not a bug: `momentum_6_1` skips the
last month and uses a 6-month window, so SNDK's +4,715% 12-1 return does
not inflate ITS cross-sectional σ. The champion's σ is inflated by a single
name, compressing 500 others inside ±1σ.

Consequence: the number of signals the product issues depends on how
extreme its most extreme name is. That is a property of the scaler, not of
the market, and it is not defensible.

## The three schemes under test

- **S-PLAIN (incumbent):** `(x - mean) / std`. Current live behaviour.
- **S-ROBUST:** `(x - median) / (1.4826 * MAD)`. Median/MAD; the 1.4826
  factor makes it consistent with σ for Gaussian data, so ±1.0σ thresholds
  keep their meaning. Outliers move the scale barely at all.
- **S-RANK:** `rank_normalize` (van der Waerden inverse-normal of
  percentile ranks) — already in the codebase for valuation/quality.
  Maximally outlier-immune; discards magnitude information entirely.

## Pre-registered decision rule (fixed BEFORE measurement)

Two candidate columns (`momentum_robust`, `momentum_ranknorm`) are computed
over the full history and judged EXACTLY like any other candidate:

1. **Predictive bar (primary, unchanged):** mean IC >= 0.02 AND t >= 2.0 at
   21d, computed by the same `gate2_ic_analysis.py`.
2. **Non-inferiority:** a challenger scheme replaces S-PLAIN only if its
   21d IC is **>= S-PLAIN's IC minus 0.002** (i.e. it may not buy stability
   with a materially worse signal). This tolerance is registered now.
3. **Stability (tie-breaker, only among schemes passing 1 and 2):** the
   scheme whose count of |score| >= 1.0 names is least sensitive to the
   single most extreme name — measured by re-scoring with the top-|z| name
   removed and recording the change in threshold-crossing count.
4. If no challenger satisfies 1+2, **S-PLAIN stays.** "The card count is
   inconvenient" is not a reason to change a scorer.

## What changes if a challenger wins

- `momentum_composite` switches to the winning scheme on a stated date.
- The champion's alpha values change => the ranking may change => this is a
  **methodology change, not a bug fix**: it gets a dated entry in CLAUDE.md,
  a note in the site methodology, and the paper-trading record is NOT
  retroactively rescored. The existing champion stream keeps its identity;
  the new scheme runs as a separate tracked model version first
  (`champion-momentum-v2`), and promotion follows the same realized-IC rule
  as everything else. No hot-swap.
- Issued signal cards are never re-scored or deleted (append-only holds).

## What this is NOT

- Not a change to the ±1.0σ card thresholds (D1 stays; only the scale
  underneath it is under test).
- Not applied to valuation/quality (already rank-normalized).
- Not a claim that more cards is better. If S-PLAIN wins on the rule above,
  the product keeps issuing few cards on outlier days, and the methodology
  page explains why.
