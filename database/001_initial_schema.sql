-- 001_initial_schema.sql
-- Verbatim from spec v3 §Database Schema (Supabase / Postgres).
-- Run in Supabase SQL editor (Step 2).

-- Companies (the universe)
create table companies (
  id uuid primary key default gen_random_uuid(),
  ticker text unique not null,
  name text not null,
  sector text,
  industry text,
  market_cap numeric,
  in_universe boolean default true,
  added_at timestamp default now()
);

-- Daily price data
create table price_features (
  id bigserial primary key,
  company_id uuid references companies(id),
  date date not null,
  open numeric, high numeric, low numeric, close numeric, volume bigint,
  rsi_14 numeric,
  macd numeric, macd_signal numeric, macd_hist numeric,
  sma_20 numeric, sma_50 numeric, sma_200 numeric,
  momentum_12_1 numeric,
  realized_vol_30d numeric,
  unique(company_id, date)
);

-- Fundamental data
create table fundamental_features (
  id bigserial primary key,
  company_id uuid references companies(id),
  as_of_date date not null,  -- point-in-time discipline
  filing_date date,
  pe_ratio numeric, forward_pe numeric, pb_ratio numeric,
  ev_ebitda numeric, fcf_yield numeric,
  roe numeric, roic numeric, gross_margin numeric,
  revenue_growth_yoy numeric, eps_growth_yoy numeric,
  unique(company_id, as_of_date)
);

-- Insider transactions
create table insider_transactions (
  id bigserial primary key,
  company_id uuid references companies(id),
  transaction_date date not null,
  filing_date date not null,
  insider_name text,
  insider_title text,
  transaction_code text,  -- 'P' = purchase, 'S' = sale
  shares numeric,
  price numeric,
  total_value numeric,
  source text default 'SEC_EDGAR'
);

-- Congressional transactions
create table congress_transactions (
  id bigserial primary key,
  company_id uuid references companies(id),
  transaction_date date not null,
  filing_date date not null,
  politician_name text,
  chamber text,  -- 'House' or 'Senate'
  party text,
  transaction_type text,  -- 'purchase', 'sale', 'exchange'
  amount_range text,
  estimated_value numeric,
  source text
);

-- Daily factor scores (computed)
create table factor_scores (
  id bigserial primary key,
  company_id uuid references companies(id),
  date date not null,
  momentum_composite numeric,
  valuation_composite numeric,
  insider_congress_composite numeric,
  -- scaffolded factor columns for future use
  earnings_composite numeric,
  sentiment_composite numeric,
  volatility_composite numeric,
  quality_composite numeric,
  unique(company_id, date)
);

-- Daily predictions
create table predictions (
  id bigserial primary key,
  company_id uuid references companies(id),
  date date not null,
  alpha_score numeric not null,
  confidence numeric,
  predicted_return_30d numeric,
  position_size numeric,
  model_version text,
  unique(company_id, date)
);

-- LLM-generated theses
create table llm_theses (
  id bigserial primary key,
  company_id uuid references companies(id),
  date date not null,
  thesis_text text,
  model text default 'claude-sonnet-4-5',
  prompt_tokens int,
  completion_tokens int,
  cost_usd numeric
);

-- Subscribers
create table subscribers (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  subscribed_at timestamp default now(),
  unsubscribed_at timestamp,
  source text
);

-- System logs
create table system_logs (
  id bigserial primary key,
  timestamp timestamp default now(),
  level text,
  component text,
  message text,
  metadata jsonb
);

-- Data quality tracking
create table data_quality_log (
  id bigserial primary key,
  date date,
  source text,  -- 'yfinance', 'sec_edgar', 'congress'
  ticker text,
  status text,  -- 'success', 'missing', 'error'
  details text
);
