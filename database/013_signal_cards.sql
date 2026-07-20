-- 013_signal_cards.sql
-- Signal Phase S1.1 (docs/SIGNAL_PHASE_SPEC.md): the public, append-only
-- signal ledger. Cards are NEVER updated after issue except by the resolver
-- filling resolution fields exactly once (status open -> hit|stop|expired).
-- Run AFTER 012_batch2_candidates.sql.

create table if not exists signal_cards (
  id bigserial primary key,
  company_id uuid not null references companies(id),
  ticker text not null,
  issue_date date not null,
  model_version text not null,
  horizon_days int not null default 21,
  direction text not null check (direction in ('BUY', 'AVOID')),
  alpha_score numeric not null,
  entry numeric not null,          -- close at issue
  target numeric not null,         -- entry * (1 + 1.5 * sigma_21)  [D2]
  stop numeric not null,           -- entry * (1 - 1.0 * sigma_21)  [D2]
  sigma_21 numeric not null,       -- realized 63d vol * sqrt(21) at issue
  expires_date date not null,      -- issue + horizon trading days
  -- resolution (filled once by the resolver, D3 close-touch rule)
  status text not null default 'open'
    check (status in ('open', 'hit', 'stop', 'expired')),
  resolved_date date,
  resolved_close numeric,
  realized_return numeric,         -- close-to-close vs entry at resolution
  unique (company_id, issue_date, horizon_days, model_version)
);

create index if not exists ix_signal_cards_status_date
  on signal_cards (status, issue_date);
create index if not exists ix_signal_cards_ticker
  on signal_cards (ticker, issue_date desc);
