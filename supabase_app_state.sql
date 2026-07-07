-- Tabela de estado compartilhado do dashboard.
-- Preferencia operacional: configurar SUPABASE_SERVICE_ROLE no Streamlit Secrets,
-- pois as rotinas server-side precisam sincronizar app_state mesmo com RLS ativo.

create table if not exists public.app_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.app_state enable row level security;

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
