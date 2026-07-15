-- 010_prediction_outcomes.sql
-- Paper trading (Step 13 / Gate 4): realized outcomes for stored
-- predictions, resolved once horizon trading days have elapsed. This is
-- the champion-vs-challenger evidence table — promotion decisions read
-- from here, never from backtests. Run AFTER 009_performance_daily.sql.

create table if not exists prediction_outcomes (
  id bigserial primary key,
  company_id uuid not null references companies(id),
  prediction_date date not null,
  model_version text not null,
  horizon_days int not null,
  resolved_date date not null,          -- prediction_date + horizon trading days
  realized_return numeric,              -- raw close-to-close
  realized_excess_return numeric,       -- vs cross-sectional mean that window
  alpha_score numeric,                  -- copied from the prediction (audit)
  predicted_return numeric,             -- copied from the prediction (audit)
  unique(company_id, prediction_date, model_version, horizon_days)
);

create index if not exists ix_outcomes_model_date
  on prediction_outcomes (model_version, prediction_date);
