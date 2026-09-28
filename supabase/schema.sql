-- Hekayet Hala Supabase schema
create extension if not exists pgcrypto;

create table if not exists public.staff_members (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text not null default 'موظف',
  role text not null default 'staff' check (role in ('owner', 'staff')),
  active boolean not null default true,
  permissions jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.products (
  id integer primary key,
  slug text not null unique,
  name text not null,
  price numeric(10,2) not null default 0 check (price >= 0),
  image text not null default '',
  description text not null default '',
  tag text not null default '',
  collection text not null default 'classic' check (collection in ('classic', 'family')),
  stock integer not null default 20 check (stock >= 0),
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create table if not exists public.site_content (
  id text primary key default 'main',
  content jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  public_id text not null unique,
  user_id uuid references auth.users(id) on delete set null,
  user_email text,
  user_name text not null,
  customer_phone text not null,
  delivery_note text,
  items jsonb not null default '[]'::jsonb,
  details text not null default '',
  total numeric(10,2) not null default 0 check (total >= 0),
  method text not null default 'whatsapp' check (method in ('whatsapp', 'internal')),
  status text not null default 'جديد' check (status in ('جديد', 'قيد التحضير', 'تم التوصيل', 'ملغى')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists orders_created_at_idx on public.orders (created_at desc);
create index if not exists orders_status_idx on public.orders (status);

create or replace function public.is_owner()
returns boolean language sql stable security definer set search_path = public
as $$ select exists(select 1 from public.staff_members where id = auth.uid() and role = 'owner' and active = true); $$;

create or replace function public.has_permission(permission_name text)
returns boolean language sql stable security definer set search_path = public
as $$
  select public.is_owner() or exists(
    select 1 from public.staff_members
    where id = auth.uid() and active = true and coalesce((permissions ->> permission_name)::boolean, false)
  );
$$;

revoke all on function public.is_owner() from public;
revoke all on function public.has_permission(text) from public;
grant execute on function public.is_owner() to authenticated;
grant execute on function public.has_permission(text) to authenticated;

alter table public.staff_members enable row level security;
alter table public.products enable row level security;
alter table public.site_content enable row level security;
alter table public.orders enable row level security;

 drop policy if exists staff_read_self_or_owner on public.staff_members;
create policy staff_read_self_or_owner on public.staff_members for select to authenticated using (id = auth.uid() or public.is_owner());
drop policy if exists staff_owner_write on public.staff_members;
create policy staff_owner_write on public.staff_members for all to authenticated using (public.is_owner()) with check (public.is_owner());

drop policy if exists products_public_read on public.products;
create policy products_public_read on public.products for select using (active = true or public.has_permission('products_write'));
drop policy if exists products_write on public.products;
create policy products_write on public.products for all to authenticated using (public.has_permission('products_write') or public.has_permission('inventory_write')) with check (public.has_permission('products_write') or public.has_permission('inventory_write'));

drop policy if exists content_public_read on public.site_content;
create policy content_public_read on public.site_content for select using (true);
drop policy if exists content_write on public.site_content;
create policy content_write on public.site_content for all to authenticated using (public.has_permission('content_write')) with check (public.has_permission('content_write'));

drop policy if exists orders_customer_create on public.orders;
create policy orders_customer_create on public.orders for insert to authenticated with check (user_id = auth.uid());
drop policy if exists orders_read on public.orders;
create policy orders_read on public.orders for select to authenticated using (public.has_permission('orders_read') or user_id = auth.uid());
drop policy if exists orders_update on public.orders;
create policy orders_update on public.orders for update to authenticated using (public.has_permission('orders_update')) with check (public.has_permission('orders_update'));
drop policy if exists orders_owner_delete on public.orders;
create policy orders_owner_delete on public.orders for delete to authenticated using (public.is_owner());

insert into storage.buckets (id, name, public) values ('product-images', 'product-images', true) on conflict (id) do update set public = true;
drop policy if exists product_images_public_read on storage.objects;
create policy product_images_public_read on storage.objects for select using (bucket_id = 'product-images');
drop policy if exists product_images_admin_insert on storage.objects;
create policy product_images_admin_insert on storage.objects for insert to authenticated with check (bucket_id = 'product-images' and (public.has_permission('products_write') or public.has_permission('inventory_write')));
drop policy if exists product_images_admin_update on storage.objects;
create policy product_images_admin_update on storage.objects for update to authenticated using (bucket_id = 'product-images' and public.has_permission('products_write'));
drop policy if exists product_images_admin_delete on storage.objects;
create policy product_images_admin_delete on storage.objects for delete to authenticated using (bucket_id = 'product-images' and public.has_permission('products_write'));

alter table public.staff_members replica identity full;
alter table public.products replica identity full;
alter table public.orders replica identity full;
alter publication supabase_realtime add table public.products;
alter publication supabase_realtime add table public.orders;
alter publication supabase_realtime add table public.staff_members;
