-- ============================================================
-- Dados de exemplo (rode DEPOIS do schema.sql).
-- Usa appids reais da Steam; o worker depois traz os precos de verdade.
-- ============================================================
insert into stores (name, slug, affiliate_code)
values ('Steam', 'steam', null)
on conflict (slug) do nothing;

insert into games (title, slug, platform, cover_url) values
 ('Elden Ring','elden-ring-pc','PC','https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg'),
 ('Hades','hades-pc','PC','https://cdn.cloudflare.steamstatic.com/steam/apps/1145360/header.jpg'),
 ('Cyberpunk 2077','cyberpunk-2077-pc','PC','https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/header.jpg'),
 ('Baldurs Gate 3','baldurs-gate-3-pc','PC','https://cdn.cloudflare.steamstatic.com/steam/apps/1086940/header.jpg'),
 ('Stardew Valley','stardew-valley-pc','PC','https://cdn.cloudflare.steamstatic.com/steam/apps/413150/header.jpg')
on conflict (slug) do nothing;

-- Ofertas (jogo + loja + appid)
insert into game_store_offers (game_id, store_id, external_id, product_url)
select g.id, s.id, v.appid, 'https://store.steampowered.com/app/' || v.appid || '/'
from (values
  ('elden-ring-pc','1245620'),
  ('hades-pc','1145360'),
  ('cyberpunk-2077-pc','1091500'),
  ('baldurs-gate-3-pc','1086940'),
  ('stardew-valley-pc','413150')
) as v(slug, appid)
join games g on g.slug = v.slug
join stores s on s.slug = 'steam'
on conflict (store_id, external_id) do nothing;

-- Um preco inicial de exemplo por oferta (o worker substitui pelos reais)
insert into prices (offer_id, price, old_price, discount_percent)
select o.id, p.price, p.old_price, p.disc
from (values
  ('1245620', 199.90, 249.90, 20),
  ('1145360', 46.99, null, 0),
  ('1091500', 99.50, 199.00, 50),
  ('1086940', 199.90, null, 0),
  ('413150', 24.99, null, 0)
) as p(appid, price, old_price, disc)
join game_store_offers o on o.external_id = p.appid;
