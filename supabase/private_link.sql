-- 私密連結：不用帳號密碼，用一條帶金鑰的連結（#k=…）存取自己的持股。
-- 資料庫只存金鑰的 SHA-256，原文只在你的連結裡。網站透過下面三個函式讀寫，金鑰不對就拒絕。
-- 已套用到專案 xpwucjblikcyvxjilkna（2026-11-08）。換新連結：產生新金鑰，把它的 SHA-256 寫進 access_keys，舊的那列刪掉。
create schema if not exists private_link;

alter table public.holdings add column if not exists removed_at timestamptz;  -- 網站上刪除＝軟刪除

create table if not exists public.access_keys (
  key_hash text primary key,
  owner uuid not null references auth.users (id) on delete cascade,
  label text not null default '',
  created_at timestamptz not null default now()
);
alter table public.access_keys enable row level security;  -- 沒有任何 policy：對外完全讀不到

create or replace function private_link.owner_of(k text) returns uuid
language sql stable security definer set search_path = '' as $$
  select owner from public.access_keys
  where key_hash = encode(extensions.digest(coalesce(k, ''), 'sha256'), 'hex')
$$;

create or replace function public.vault_data(k text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare o uuid := private_link.owner_of(k);
begin
  if o is null then raise exception 'invalid key' using errcode = '28000'; end if;
  return jsonb_build_object(
    'holdings', (select coalesce(jsonb_agg(to_jsonb(h) order by h.symbol, h.id), '[]'::jsonb)
                 from public.holdings h where h.user_id = o and h.removed_at is null),
    'report', (select r.report from public.holdings_reports r where r.user_id = o));
end $$;

create or replace function public.vault_save_holding(k text, h jsonb) returns bigint
language plpgsql security definer set search_path = '' as $$
declare o uuid := private_link.owner_of(k); hid bigint;
begin
  if o is null then raise exception 'invalid key' using errcode = '28000'; end if;
  if nullif(h->>'id', '') is not null then
    update public.holdings set
      symbol = upper(trim(h->>'symbol')), name = coalesce(h->>'name', ''),
      shares = (h->>'shares')::numeric, avg_cost = (h->>'avg_cost')::numeric,
      buy_date = nullif(h->>'buy_date', '')::date, account = coalesce(h->>'account', ''),
      sector = coalesce(h->>'sector', ''), thesis = coalesce(h->>'thesis', ''),
      fx_cost = nullif(h->>'fx_cost', '')::numeric
    where id = (h->>'id')::bigint and user_id = o and removed_at is null
    returning id into hid;
    if hid is null then raise exception 'not found'; end if;
  else
    insert into public.holdings (user_id, symbol, name, shares, avg_cost, buy_date, account, sector, thesis, fx_cost)
    values (o, upper(trim(h->>'symbol')), coalesce(h->>'name', ''), (h->>'shares')::numeric, (h->>'avg_cost')::numeric,
            nullif(h->>'buy_date', '')::date, coalesce(h->>'account', ''), coalesce(h->>'sector', ''),
            coalesce(h->>'thesis', ''), nullif(h->>'fx_cost', '')::numeric)
    returning id into hid;
  end if;
  return hid;
end $$;

create or replace function public.vault_remove_holding(k text, hid bigint) returns void
language plpgsql security definer set search_path = '' as $$
declare o uuid := private_link.owner_of(k);
begin
  if o is null then raise exception 'invalid key' using errcode = '28000'; end if;
  update public.holdings set removed_at = now() where id = hid and user_id = o;
end $$;
