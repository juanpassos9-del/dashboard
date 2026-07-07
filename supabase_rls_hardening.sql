-- Supabase RLS hardening for Terminal TTS.
-- Execute this full file in Supabase SQL Editor.
-- Order matters: profiles first, then app_state.

create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  email text not null,
  phone text,
  role text not null default 'member' check (role in ('admin', 'member')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists profiles_phone_idx on public.profiles (phone);

alter table public.profiles
add column if not exists role text not null default 'member';

create index if not exists profiles_role_idx on public.profiles (role);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_role_check'
  ) then
    alter table public.profiles
    add constraint profiles_role_check check (role in ('admin', 'member'));
  end if;
end $$;

update public.profiles
set role = 'admin',
    updated_at = now()
where id = (
  select id
  from public.profiles
  where not exists (
    select 1 from public.profiles where role = 'admin'
  )
  order by created_at asc
  limit 1
);

alter table public.profiles enable row level security;

create or replace function public.is_profile_admin()
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles p
    where p.user_id = auth.uid()
      and p.role = 'admin'
      and p.is_active = true
  );
$$;

revoke all on function public.is_profile_admin() from public;
grant execute on function public.is_profile_admin() to authenticated;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
on public.profiles
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "profiles_select_admin" on public.profiles;
create policy "profiles_select_admin"
on public.profiles
for select
to authenticated
using (public.is_profile_admin());

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own"
on public.profiles
for insert
to authenticated
with check (
  auth.uid() = user_id
  and role = 'member'
);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
on public.profiles
for update
to authenticated
using (auth.uid() = user_id)
with check (
  auth.uid() = user_id
  and role = 'member'
);

drop policy if exists "profiles_update_admin" on public.profiles;
create policy "profiles_update_admin"
on public.profiles
for update
to authenticated
using (public.is_profile_admin())
with check (public.is_profile_admin());

create table if not exists public.app_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.app_state enable row level security;

drop policy if exists "app_state_select_authenticated" on public.app_state;
create policy "app_state_select_authenticated"
on public.app_state
for select
to authenticated
using (true);

drop policy if exists "app_state_admin_insert" on public.app_state;
create policy "app_state_admin_insert"
on public.app_state
for insert
to authenticated
with check (
  public.is_profile_admin()
  and key in (
    'ai_insight',
    'ai_insight_history',
    'boletim_focus',
    'calendario_economico',
    'dados_mercado',
    'financial_juice_news',
    'fluxo_estrangeiro_b3',
    'manual_trades',
    'market_report',
    'market_report_daily',
    'mercados_globais',
    'risk_manual_trades'
  )
);

drop policy if exists "app_state_admin_update" on public.app_state;
create policy "app_state_admin_update"
on public.app_state
for update
to authenticated
using (public.is_profile_admin())
with check (
  public.is_profile_admin()
  and key in (
    'ai_insight',
    'ai_insight_history',
    'boletim_focus',
    'calendario_economico',
    'dados_mercado',
    'financial_juice_news',
    'fluxo_estrangeiro_b3',
    'manual_trades',
    'market_report',
    'market_report_daily',
    'mercados_globais',
    'risk_manual_trades'
  )
);
