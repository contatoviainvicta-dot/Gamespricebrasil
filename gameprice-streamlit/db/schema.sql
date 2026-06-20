-- ============================================================
-- GamePrice Brasil - Schema do Supabase
-- Cole tudo no Supabase > SQL Editor > New query > Run
-- ============================================================
create extension if not exists pgcrypto;

-- ---------- Tabelas ----------
create table if not exists stores (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  slug text not null unique,
  logo_url text,
  affiliate_code text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists games (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  slug text not null unique,
  platform text not null check (platform in ('PC','PS4','PS5','XBOX','SWITCH')),
  cover_url text,
  created_at timestamptz not null default now()
);
create index if not exists ix_games_platform on games(platform);
create index if not exists ix_games_title_trgm on games using gin (to_tsvector('portuguese', title));

create table if not exists game_store_offers (
  id uuid primary key default gen_random_uuid(),
  game_id uuid not null references games(id) on delete cascade,
  store_id uuid not null references stores(id) on delete cascade,
  external_id text not null,        -- ex.: appid da Steam (1245620)
  product_url text not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (store_id, external_id)
);
create index if not exists ix_offers_game on game_store_offers(game_id);

create table if not exists prices (
  id uuid primary key default gen_random_uuid(),
  offer_id uuid not null references game_store_offers(id) on delete cascade,
  price numeric(10,2) not null,
  old_price numeric(10,2),
  discount_percent int,
  available boolean not null default true,
  captured_at timestamptz not null default now()  -- serie temporal: nunca sobrescreve
);
create index if not exists ix_prices_offer_time on prices(offer_id, captured_at desc);

create table if not exists alerts (
  id uuid primary key default gen_random_uuid(),
  user_email text not null,
  game_id uuid not null references games(id) on delete cascade,
  target_price numeric(10,2) not null,
  active boolean not null default true,
  last_notified_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists ix_alerts_game on alerts(game_id);

-- ---------- Views (fazem o trabalho pesado no banco) ----------
-- Ultimo preco de cada oferta
create or replace view v_latest_prices
with (security_invoker = true) as
select distinct on (offer_id)
  offer_id, price, old_price, discount_percent, available, captured_at
from prices
order by offer_id, captured_at desc;

-- Cada jogo com suas ofertas e o preco mais recente de cada loja
create or replace view v_game_offers
with (security_invoker = true) as
select
  g.id as game_id, g.title, g.slug, g.platform, g.cover_url,
  s.name as store, s.slug as store_slug, s.affiliate_code,
  o.id as offer_id, o.product_url,
  lp.price, lp.old_price, lp.discount_percent, lp.available, lp.captured_at
from games g
join game_store_offers o on o.game_id = g.id and o.active
join stores s on s.id = o.store_id and s.active
left join v_latest_prices lp on lp.offer_id = o.id;

-- ---------- Seguranca (RLS) ----------
-- Leitura publica (anon) nas tabelas de catalogo; escrita so via service_role (worker).
alter table stores enable row level security;
alter table games enable row level security;
alter table game_store_offers enable row level security;
alter table prices enable row level security;
alter table alerts enable row level security;

create policy "leitura publica stores"  on stores  for select using (true);
create policy "leitura publica games"   on games   for select using (true);
create policy "leitura publica offers"  on game_store_offers for select using (true);
create policy "leitura publica prices"  on prices  for select using (true);

-- Qualquer visitante pode criar e ver alertas (MVP). Refine quando ligar o Supabase Auth.
create policy "criar alertas"  on alerts for insert with check (true);
create policy "ler alertas"    on alerts for select using (true);
