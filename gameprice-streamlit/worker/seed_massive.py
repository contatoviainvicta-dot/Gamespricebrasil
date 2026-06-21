"""Seed massivo: importa top 5000 jogos do Steam via SteamSpy.

Roda UMA VEZ via workflow seed-massive no GitHub Actions.
Após rodar, o catálogo sai de ~750 para ~5000 jogos.
O update-prices já cuida de atualizar os preços automaticamente.
"""
import os, sys, time
import httpx
from slugify import slugify
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

STEAM_COVER = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
STEAM_URL   = "https://store.steampowered.com/app/{appid}/"
PAGES       = 5   # 5 páginas × 1000 jogos = top 5000 mais populares


def fetch_steamspy_page(page: int) -> dict:
    """Busca uma página de jogos do SteamSpy."""
    try:
        r = httpx.get(
            "https://steamspy.com/api.php",
            params={"request": "all", "page": page},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [steamspy] erro página {page}: {e}")
        return {}


def run() -> None:
    sb = create_client(URL, KEY)

    # Buscar IDs já existentes no banco
    print("Carregando appids existentes...")
    existentes = {
        o["external_id"]
        for o in sb.table("game_store_offers")
        .select("external_id")
        .execute().data
    }
    print(f"  {len(existentes)} ofertas já no banco")

    # Buscar store_id da Steam
    steam = sb.table("stores").select("id").eq("slug", "steam").execute().data
    if not steam:
        print("ERRO: loja Steam não encontrada")
        return
    steam_id = steam[0]["id"]

    total_novos = 0
    total_skip  = 0

    for page in range(PAGES):
        print(f"\n=== Página {page+1}/{PAGES} (jogos {page*1000+1}–{(page+1)*1000}) ===")
        jogos = fetch_steamspy_page(page)
        if not jogos:
            print("  Sem dados, pulando...")
            time.sleep(2)
            continue

        print(f"  {len(jogos)} jogos recebidos")
        time.sleep(1.5)  # Rate limit SteamSpy

        # Filtrar os que já existem
        novos = {
            appid: info for appid, info in jogos.items()
            if str(appid) not in existentes
            and info.get("name")
            and not info["name"].startswith("Untitled")
        }
        print(f"  {len(novos)} novos para inserir | {len(jogos)-len(novos)} já existem")
        total_skip += len(jogos) - len(novos)

        if not novos:
            continue

        # Inserir em lotes de 50
        items = list(novos.items())
        for batch_start in range(0, len(items), 50):
            batch = items[batch_start:batch_start+50]

            # 1. Inserir jogos
            games_batch = []
            for appid, info in batch:
                title = info["name"].strip()
                slug  = slugify(f"{title}-pc")
                games_batch.append({
                    "title":     title,
                    "slug":      slug,
                    "platform":  "PC",
                    "cover_url": STEAM_COVER.format(appid=appid),
                })

            try:
                result = sb.table("games").upsert(
                    games_batch, on_conflict="slug"
                ).execute()
            except Exception as e:
                print(f"  Erro ao inserir jogos: {e}")
                continue

            # 2. Buscar IDs gerados
            slugs = [g["slug"] for g in games_batch]
            game_rows = sb.table("games").select("id,slug")\
                          .in_("slug", slugs).execute().data
            slug_to_id = {r["slug"]: r["id"] for r in game_rows}

            # 3. Inserir ofertas Steam
            offers_batch = []
            for appid, info in batch:
                title = info["name"].strip()
                slug  = slugify(f"{title}-pc")
                game_id = slug_to_id.get(slug)
                if not game_id:
                    continue
                offers_batch.append({
                    "game_id":     game_id,
                    "store_id":    steam_id,
                    "external_id": str(appid),
                    "product_url": STEAM_URL.format(appid=appid),
                    "active":      True,
                })
                existentes.add(str(appid))

            if offers_batch:
                try:
                    sb.table("game_store_offers").upsert(
                        offers_batch, on_conflict="store_id,external_id"
                    ).execute()
                    total_novos += len(offers_batch)
                    print(f"  ✓ Lote {batch_start//50+1}: {len(offers_batch)} inseridos "
                          f"(ex: {batch[0][1]['name'][:30]}...)")
                except Exception as e:
                    print(f"  Erro ao inserir ofertas: {e}")

            time.sleep(0.2)  # Pausa entre lotes para não sobrecarregar Supabase

    # Resumo final
    total_jogos  = len(sb.table("games").select("id").execute().data)
    total_ofertas = len(sb.table("game_store_offers").select("id").execute().data)
    print(f"\n{'='*50}")
    print(f"Seed massivo concluído!")
    print(f"  Novos inseridos: {total_novos}")
    print(f"  Já existiam:     {total_skip}")
    print(f"  Total no banco:  {total_jogos:,} jogos")
    print(f"  Total ofertas:   {total_ofertas:,} ofertas")
    print(f"{'='*50}")
    print(f"\nPróximo passo: rode o workflow update-prices para buscar os preços")


if __name__ == "__main__":
    run()
