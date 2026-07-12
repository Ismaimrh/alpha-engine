-- 007_predictions_model_version.sql
-- Champion/challenger (Step 8.2 decision, 2026-07-10): two models write
-- predictions per (company, date), so model_version joins the uniqueness
-- key. Run AFTER 006_gate1_function.sql.

alter table predictions
  drop constraint if exists predictions_company_id_date_key;

create unique index if not exists uq_predictions_company_date_model
  on predictions (company_id, date, model_version);
