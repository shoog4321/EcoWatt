-- Run once in the Supabase SQL editor.
-- Job state lives in its OWN table so users cannot tamper with it: your "Bill" UPDATE policy lets a user
-- edit every column of their own bills. Here clients may only READ their jobs; only the backend
-- (service-role key, which bypasses RLS) writes.

create table if not exists public.advice_jobs (
  bill_id     uuid primary key references public."Bill"(bill_id) on delete cascade,
  status      text not null default 'pending' check (status in ('pending','running','done','failed')),
  error       text,
  analysis    jsonb,                       -- rule-engine output used as the LLM input
  audit       jsonb,                       -- per-item safety outcome (ok / repaired / prefixed / unresolved)
  updated_at  timestamptz not null default now()
);

alter table public.advice_jobs enable row level security;

create policy "Users can view own advice jobs" on public.advice_jobs
  for select to authenticated
  using (exists (
    select 1 from public."Bill" b join public."Household" h on h.household_id = b.household_id
    where b.bill_id = advice_jobs.bill_id and h.user_id = auth.uid()));
-- deliberately NO insert/update/delete policies

create index if not exists advice_jobs_pending_idx on public.advice_jobs (updated_at) where status = 'pending';

-- Links each stored advice row to the approved catalog entry (e.g. ADV_004) for audit.
alter table public."Advice" add column if not exists catalog_advice_id text;

-- Optional: let Flutter get live updates instead of polling
-- alter publication supabase_realtime add table public.advice_jobs;
