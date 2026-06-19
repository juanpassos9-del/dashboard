-- Tabela de estado compartilhado do dashboard.
-- Preferencia operacional: configurar SUPABASE_SERVICE_ROLE no Streamlit Secrets,
-- pois as rotinas server-side precisam sincronizar app_state mesmo com RLS ativo.

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
  exists (
    select 1
    from public.profiles p
    where p.user_id = auth.uid()
      and p.role = 'admin'
      and p.is_active = true
  )
);

drop policy if exists "app_state_admin_update" on public.app_state;
create policy "app_state_admin_update"
on public.app_state
for update
to authenticated
using (
  exists (
    select 1
    from public.profiles p
    where p.user_id = auth.uid()
      and p.role = 'admin'
      and p.is_active = true
  )
)
with check (
  exists (
    select 1
    from public.profiles p
    where p.user_id = auth.uid()
      and p.role = 'admin'
      and p.is_active = true
  )
);
