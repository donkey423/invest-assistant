-- 我的資產：持股、交易紀錄、每日計算結果。
-- 在 Supabase 後台 → SQL Editor 整份貼上執行一次即可（重複執行也安全）。
-- 每個人只能看到、改到自己的資料（Row Level Security）；排程用 secret 金鑰寫入計算結果。

create table if not exists public.holdings (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  symbol text not null check (char_length(symbol) between 1 and 20),
  name text not null default '' check (char_length(name) <= 60),
  shares numeric not null check (shares > 0),
  avg_cost numeric not null check (avg_cost >= 0),
  buy_date date,
  account text not null default '' check (char_length(account) <= 40),
  sector text not null default '' check (char_length(sector) <= 40),
  thesis text not null default '' check (char_length(thesis) <= 500),
  fx_cost numeric check (fx_cost > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists holdings_user_id_idx on public.holdings (user_id);

create table if not exists public.transactions (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  date date not null,
  symbol text not null check (char_length(symbol) between 1 and 20),
  type text not null check (type in ('sell', 'dividend')),
  shares numeric not null default 0,
  price numeric not null default 0,
  avg_cost numeric not null default 0,
  amount numeric not null default 0,
  fee numeric not null default 0,
  account text not null default '',
  created_at timestamptz not null default now()
);
create index if not exists transactions_user_id_idx on public.transactions (user_id);

create table if not exists public.holdings_reports (
  user_id uuid primary key references auth.users (id) on delete cascade,
  report jsonb not null,
  generated_at timestamptz not null default now()
);

create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists holdings_touch on public.holdings;
create trigger holdings_touch before update on public.holdings
  for each row execute function public.touch_updated_at();

alter table public.holdings enable row level security;
alter table public.transactions enable row level security;
alter table public.holdings_reports enable row level security;

-- 持股與交易：本人可讀寫
drop policy if exists "own holdings" on public.holdings;
create policy "own holdings" on public.holdings for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "own transactions" on public.transactions;
create policy "own transactions" on public.transactions for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
-- 計算結果：本人只能讀，寫入只有排程（secret 金鑰會略過 RLS）
drop policy if exists "read own report" on public.holdings_reports;
create policy "read own report" on public.holdings_reports for select to authenticated
  using ((select auth.uid()) = user_id);

-- 沒登入的人什麼都拿不到
revoke all on public.holdings, public.transactions, public.holdings_reports from anon;
