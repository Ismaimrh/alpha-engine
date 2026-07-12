-- 009_performance_daily.sql
-- Precomputed backtest equity series (Step 11.5): the /api/performance
-- endpoint must answer in milliseconds, while the walk-forward backtest
-- takes minutes — so scripts/export_performance.py computes and upserts
-- here (rerun after factor backfills). Run AFTER 008_theses_dedup.sql.

create table if not exists performance_daily (
  id bigserial primary key,
  date date not null,
  strategy_return numeric,
  benchmark_return numeric,
  strategy_equity numeric,   -- cumulative growth of 1
  benchmark_equity numeric,
  params jsonb,              -- {top_n, rebalance, cost_bps} for provenance
  unique(date)
);
