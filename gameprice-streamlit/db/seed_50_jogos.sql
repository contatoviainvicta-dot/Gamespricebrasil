-- ============================================================
-- GamePrice Brasil - Catálogo expandido: 50 jogos Steam
-- Cole no Supabase > SQL Editor > Run
-- DEPOIS do schema.sql já aplicado.
-- Os preços reais chegam na próxima execução do worker.
-- ============================================================

-- Garante que a loja Steam existe
insert into stores (name, slug, affiliate_code)
values ('Steam', 'steam', null)
on conflict (slug) do nothing;

-- -------------------------------------------------------
-- Jogos (title, slug, platform, cover_url, appid Steam)
-- -------------------------------------------------------
with novos_jogos (title, slug, appid) as (values
  -- Ação / RPG
  ('Elden Ring',                    'elden-ring-pc',                '1245620'),
  ('Cyberpunk 2077',                'cyberpunk-2077-pc',            '1091500'),
  ('Baldur''s Gate 3',              'baldurs-gate-3-pc',            '1086940'),
  ('Dark Souls III',                'dark-souls-3-pc',              '374320'),
  ('Sekiro: Shadows Die Twice',     'sekiro-pc',                    '814380'),
  ('Monster Hunter: World',         'monster-hunter-world-pc',      '582010'),
  ('Monster Hunter Rise',           'monster-hunter-rise-pc',       '1446780'),
  ('The Witcher 3',                 'witcher-3-pc',                 '292030'),
  ('Hogwarts Legacy',               'hogwarts-legacy-pc',           '990080'),
  ('Assassin''s Creed Mirage',      'assassins-creed-mirage-pc',    '2073490'),
  -- FPS / Ação
  ('Counter-Strike 2',              'cs2-pc',                       '730'),
  ('Grand Theft Auto V',            'gta-5-pc',                     '271590'),
  ('Red Dead Redemption 2',         'rdr2-pc',                      '1174180'),
  ('Halo Infinite',                 'halo-infinite-pc',             '1240440'),
  ('DOOM Eternal',                  'doom-eternal-pc',              '782330'),
  ('Titanfall 2',                   'titanfall-2-pc',               '1237970'),
  ('Battlefield V',                 'battlefield-v-pc',             '877480'),
  ('Call of Duty: Black Ops 6',     'cod-black-ops-6-pc',           '2933620'),
  -- Indie / Plataforma
  ('Hades',                         'hades-pc',                     '1145360'),
  ('Hades II',                      'hades-2-pc',                   '1145350'),
  ('Stardew Valley',                'stardew-valley-pc',            '413150'),
  ('Hollow Knight',                 'hollow-knight-pc',             '367520'),
  ('Celeste',                       'celeste-pc',                   '504230'),
  ('Cuphead',                       'cuphead-pc',                   '268910'),
  ('Ori and the Will of the Wisps', 'ori-will-wisps-pc',            '1057090'),
  ('Dead Cells',                    'dead-cells-pc',                '588650'),
  ('Terraria',                      'terraria-pc',                  '105600'),
  ('Disco Elysium',                 'disco-elysium-pc',             '632470'),
  -- Survival / Sandbox
  ('Minecraft (Java)',               'minecraft-java-pc',            '2357570'),
  ('Valheim',                       'valheim-pc',                   '892970'),
  ('Subnautica',                    'subnautica-pc',                '264710'),
  ('The Forest',                    'the-forest-pc',                '242760'),
  ('Sons of the Forest',            'sons-of-the-forest-pc',        '1326470'),
  ('Satisfactory',                  'satisfactory-pc',              '526870'),
  ('Factorio',                      'factorio-pc',                  '427520'),
  ('RimWorld',                      'rimworld-pc',                  '294100'),
  -- Estratégia / Simulação
  ('Civilization VI',               'civilization-6-pc',            '289070'),
  ('Total War: Warhammer III',      'total-war-warhammer-3-pc',     '1142710'),
  ('Cities: Skylines II',           'cities-skylines-2-pc',         '949230'),
  ('Football Manager 2024',         'football-manager-2024-pc',     '2252570'),
  -- Corrida / Esportes
  ('F1 24',                         'f1-24-pc',                     '2488620'),
  ('EA Sports FC 25',               'ea-fc-25-pc',                  '2195250'),
  ('Forza Horizon 5',               'forza-horizon-5-pc',           '1551360'),
  -- Aventura / Narrativa
  ('A Plague Tale: Requiem',        'plague-tale-requiem-pc',       '1812040'),
  ('God of War',                    'god-of-war-pc',                '1593500'),
  ('Spider-Man Remastered',         'spider-man-remastered-pc',     '1817070'),
  ('Spider-Man: Miles Morales',     'spider-man-miles-morales-pc',  '1817190'),
  ('Horizon Zero Dawn',             'horizon-zero-dawn-pc',         '1151640'),
  ('Detroit: Become Human',         'detroit-become-human-pc',      '1222140'),
  ('It Takes Two',                  'it-takes-two-pc',              '1426210')
)
insert into games (title, slug, platform, cover_url)
select
  nj.title,
  nj.slug,
  'PC',
  'https://cdn.cloudflare.steamstatic.com/steam/apps/' || nj.appid || '/header.jpg'
from novos_jogos nj
on conflict (slug) do nothing;

-- -------------------------------------------------------
-- Ofertas: liga cada jogo à loja Steam com o appid
-- -------------------------------------------------------
with mapa (slug, appid) as (values
  ('elden-ring-pc','1245620'),('cyberpunk-2077-pc','1091500'),
  ('baldurs-gate-3-pc','1086940'),('dark-souls-3-pc','374320'),
  ('sekiro-pc','814380'),('monster-hunter-world-pc','582010'),
  ('monster-hunter-rise-pc','1446780'),('witcher-3-pc','292030'),
  ('hogwarts-legacy-pc','990080'),('assassins-creed-mirage-pc','2073490'),
  ('cs2-pc','730'),('gta-5-pc','271590'),('rdr2-pc','1174180'),
  ('halo-infinite-pc','1240440'),('doom-eternal-pc','782330'),
  ('titanfall-2-pc','1237970'),('battlefield-v-pc','877480'),
  ('cod-black-ops-6-pc','2933620'),('hades-pc','1145360'),
  ('hades-2-pc','1145350'),('stardew-valley-pc','413150'),
  ('hollow-knight-pc','367520'),('celeste-pc','504230'),
  ('cuphead-pc','268910'),('ori-will-wisps-pc','1057090'),
  ('dead-cells-pc','588650'),('terraria-pc','105600'),
  ('disco-elysium-pc','632470'),('minecraft-java-pc','2357570'),
  ('valheim-pc','892970'),('subnautica-pc','264710'),
  ('the-forest-pc','242760'),('sons-of-the-forest-pc','1326470'),
  ('satisfactory-pc','526870'),('factorio-pc','427520'),
  ('rimworld-pc','294100'),('civilization-6-pc','289070'),
  ('total-war-warhammer-3-pc','1142710'),('cities-skylines-2-pc','949230'),
  ('football-manager-2024-pc','2252570'),('f1-24-pc','2488620'),
  ('ea-fc-25-pc','2195250'),('forza-horizon-5-pc','1551360'),
  ('plague-tale-requiem-pc','1812040'),('god-of-war-pc','1593500'),
  ('spider-man-remastered-pc','1817070'),('spider-man-miles-morales-pc','1817190'),
  ('horizon-zero-dawn-pc','1151640'),('detroit-become-human-pc','1222140'),
  ('it-takes-two-pc','1426210')
)
insert into game_store_offers (game_id, store_id, external_id, product_url)
select
  g.id,
  s.id,
  m.appid,
  'https://store.steampowered.com/app/' || m.appid || '/'
from mapa m
join games g on g.slug = m.slug
join stores s on s.slug = 'steam'
on conflict (store_id, external_id) do nothing;

-- Mensagem de confirmação
select
  'Catálogo expandido' as status,
  count(*) as total_jogos
from games
where platform = 'PC';
