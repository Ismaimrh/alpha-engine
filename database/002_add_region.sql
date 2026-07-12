-- 002_add_region.sql
-- Multi-region readiness (decision v3.1: US-only MVP, Europe in Phase 6).
-- Run in the Supabase SQL editor AFTER 001_initial_schema.sql.

alter table companies
  add column if not exists region text not null default 'US',
  add column if not exists exchange text,          -- e.g. 'NYSE', 'NASDAQ', 'EPA' (Euronext Paris)
  add column if not exists currency text not null default 'USD';

-- Cross-sectional factor math must never mix currencies/regions blindly:
-- future queries should filter on region. Index accordingly.
create index if not exists idx_companies_region on companies (region)
  where in_universe = true;
