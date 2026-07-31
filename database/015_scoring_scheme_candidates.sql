-- 015_scoring_scheme_candidates.sql
-- Momentum scoring-scheme candidates (docs/ROBUST_Z_PREREG.md, registered
-- 2026-07-22): median/MAD and rank-normal variants of the SAME composite.
-- Standalone columns; the live momentum_composite is unchanged until a
-- challenger wins the pre-registered decision rule. Run AFTER 014.

alter table factor_scores
  add column if not exists momentum_robust numeric,
  add column if not exists momentum_ranknorm numeric;
