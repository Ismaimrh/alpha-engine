-- 014_batch3_candidates.sql
-- Research batch 3 candidate columns (2026-07-19, price/volume-derived, no
-- new data sources): 52-week-high proximity, 6-1 medium-horizon momentum,
-- abnormal dollar volume. Standalone columns; live composite untouched
-- until each passes Gate 2. Run AFTER 013_signal_cards.sql.

alter table factor_scores
  add column if not exists high_52w numeric,
  add column if not exists momentum_6_1 numeric,
  add column if not exists abnormal_volume numeric;
