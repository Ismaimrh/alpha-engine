-- 012_batch2_candidates.sql
-- Research batch 2 candidate columns (2026-07-16): sector-relative
-- momentum, 21d short-term reversal, low-volatility. Standalone columns;
-- the live composite/champion are untouched until each passes Gate 2 on
-- its own. Run AFTER 011_insider_v2.sql.

alter table factor_scores
  add column if not exists momentum_sector_rel numeric,
  add column if not exists reversal_21d numeric,
  add column if not exists low_vol numeric;
