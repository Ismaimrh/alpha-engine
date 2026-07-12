-- 008_theses_dedup.sql
-- Same schema-gap class as 004/005/007: llm_theses had no unique key, so
-- regenerating a day's theses would duplicate rows (and re-spend API cost
-- invisibly). Run AFTER 007_predictions_model_version.sql.

create unique index if not exists uq_theses_company_date_model
  on llm_theses (company_id, date, model);
