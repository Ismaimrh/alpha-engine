-- 005_congress_dedup.sql
-- Same schema gap as 004: congress_transactions had no unique key, so
-- re-running a backfill would duplicate rows. Source dumps carry no stable
-- per-row id, so we use a deterministic content hash computed by the
-- loader. Run AFTER 004_insider_dedup.sql.

alter table congress_transactions
  add column if not exists row_key text;

create unique index if not exists uq_congress_row_key
  on congress_transactions (row_key);
