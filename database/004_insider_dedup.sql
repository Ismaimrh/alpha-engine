-- 004_insider_dedup.sql
-- The spec schema gave insider_transactions no unique key, so re-running a
-- backfill would duplicate every row. The SEC accession number + the
-- transaction's sequence within the filing is a natural, stable key.
-- Run in the Supabase SQL editor AFTER 003_add_eps_std.sql.

alter table insider_transactions
  add column if not exists accession_no text,
  add column if not exists row_seq int;

create unique index if not exists uq_insider_accession_row
  on insider_transactions (accession_no, row_seq);
