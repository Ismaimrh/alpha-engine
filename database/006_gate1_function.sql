-- 006_gate1_function.sql
-- Server-side Gate 1 data-quality report. All aggregates computed in
-- Postgres (fast, no row shipping); scripts/gate1_check.py calls this via
-- RPC and applies pass/fail thresholds. Run AFTER 005_congress_dedup.sql.

create or replace function gate1_report()
returns jsonb
language sql
stable
as $$
select jsonb_build_object(
  'universe', (
    select jsonb_build_object(
      'companies_in_universe', count(*) filter (where in_universe),
      'with_market_cap',       count(*) filter (where in_universe and market_cap is not null)
    ) from companies
  ),
  'prices', (
    select jsonb_build_object(
      'total_rows',        count(*),
      'distinct_companies', count(distinct company_id),
      'min_date',          min(date),
      'max_date',          max(date),
      'null_close_rows',   count(*) filter (where close is null),
      'momentum_nonnull_last_day',
        count(*) filter (where date = (select max(date) from price_features)
                         and momentum_12_1 is not null)
    ) from price_features
  ),
  'fundamentals', (
    select jsonb_build_object(
      'total_rows',         count(*),
      'distinct_companies', count(distinct company_id),
      'latest_as_of',       max(as_of_date),
      'null_pe',            count(*) filter (where pe_ratio is null),
      'null_roe',           count(*) filter (where roe is null),
      'null_fcf_yield',     count(*) filter (where fcf_yield is null),
      'null_eps_std_3y',    count(*) filter (where eps_std_3y is null)
    ) from fundamental_features
  ),
  'insider', (
    select jsonb_build_object(
      'total_rows',          count(*),
      'distinct_companies',  count(distinct company_id),
      'min_transaction',     min(transaction_date),
      'max_transaction',     max(transaction_date),
      'max_filing',          max(filing_date),
      'pit_violations',      count(*) filter (where transaction_date > filing_date),
      'buys',                count(*) filter (where transaction_code = 'P'),
      'sells',               count(*) filter (where transaction_code = 'S')
    ) from insider_transactions
  ),
  'congress', (
    select jsonb_build_object(
      'total_rows',         count(*),
      'distinct_companies', count(distinct company_id),
      'house_rows',         count(*) filter (where chamber = 'House'),
      'senate_rows',        count(*) filter (where chamber = 'Senate'),
      'max_filing',         max(filing_date),
      'pit_violations',     count(*) filter (where transaction_date > filing_date)
    ) from congress_transactions
  ),
  'quality_log', (
    select coalesce(jsonb_object_agg(k, v), '{}'::jsonb) from (
      select source || ':' || status as k, count(*) as v
      from data_quality_log
      group by source, status
    ) t
  )
);
$$;
