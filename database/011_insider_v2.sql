-- 011_insider_v2.sql
-- Candidate factor column (Step 15 / research cycle 1): buys-only insider
-- signal v2. Standalone column; the live composite is untouched until v2
-- passes Gate 2 IC on its own merits. Run AFTER 010_prediction_outcomes.sql.

alter table factor_scores
  add column if not exists insider_v2 numeric;
