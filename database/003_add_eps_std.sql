-- 003_add_eps_std.sql
-- The quality composite (spec Phase 2: "earnings stability = 3Y std dev of
-- EPS") needs eps_std_3y, which the spec's schema omitted. Run in the
-- Supabase SQL editor AFTER 002_add_region.sql.

alter table fundamental_features
  add column if not exists eps_std_3y numeric;
