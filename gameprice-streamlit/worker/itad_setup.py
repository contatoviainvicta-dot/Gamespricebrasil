"""Setup inicial do ITAD: descobre os ITAD IDs dos jogos do catálogo
e atualiza o banco com as ofertas no formato ITAD|SHOP|ITAD_ID.

Rode UMA VEZ depois de configurar ITAD_API_KEY nos secrets do GitHub.
Depois o update_prices.py já cuida da atualização automática.
"""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import itad_lookup_by_title, itad_prices_batch, ITAD_SHOPS

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]
ITAD_KEY_CHECK = os.environ.get("ITAD_API_KEY", "")

# Lojas que vamos vincular via ITAD
SHOP_SLUGS = ["gog", "epic", "nuuvem", "fanatical", "humblestore"]


def run() -> None:
    if not ITAD_KEY_CHECK:
        print("ERRO: ITAD_API_KEY não configurado nos secrets")
        return

    sb = create_client(URL, KEY)

    # Buscar IDs das lojas ITAD no banco
    lojas = {s["slug"]: s["id"] for s in
             sb.table("stores").select("id,slug").execute().data}

    # Garantir que as lojas existem
    for slug, nome in [("gog","GOG"),("epic","Epic Games"),
                       ("nuuvem","Nuuvem"),("fanatical","Fanatical"),
                       ("humblestore","Humble Store")]:
        if slug not in lojas:
            r = sb.table("stores").upsert(
                {"name": nome, "slug": slug, "active": True},
                on_conflict="slug"
            ).execute()
            lojas[slug] = r.data[0]["id"]
            print(f"  Loja criada: {nome}")

    # Buscar todos os jogos PC do catálogo
    jogos = sb.table("games").select("id,title,slug")\
              .eq("platform","PC").order("title").execute().data
    print(f"{len(jogos)} jogos PC para indexar no ITAD")

    novos = 0
    erros = 0

    for i, jogo in enumerate(jogos, 1):
        title = jogo["title"]
        print(f"  [{i}/{len(jogos)}] {title[:40]}...", end=" ")

        # Buscar ITAD ID
        itad_id = itad_lookup_by_title(title)
        if not itad_id:
            print("sem ITAD ID")
            erros += 1
            time.sleep(0.3)
            continue

        # Buscar preços disponíveis
        prices = itad_prices_batch([itad_id])
        deals  = prices.get(itad_id, [])

        lojas_encontradas = [d["shop"] for d in deals if d["shop"] in SHOP_SLUGS]

        if not lojas_encontradas:
            print("sem deals")
            time.sleep(0.3)
            continue

        print(f"lojas: {lojas_encontradas}")

        # Inserir ofertas no banco
        for deal in deals:
            shop_slug = deal["shop"]
            if shop_slug not in SHOP_SLUGS or shop_slug not in lojas:
                continue
            external_id = f"ITAD|{shop_slug}|{itad_id}"
            product_url = deal.get("url", f"https://isthereanydeal.com/game/{itad_id}/info/")

            sb.table("game_store_offers").upsert({
                "game_id":     jogo["id"],
                "store_id":    lojas[shop_slug],
                "external_id": external_id,
                "product_url": product_url,
                "active":      True,
            }, on_conflict="store_id,external_id").execute()
            novos += 1

        time.sleep(0.15)  # Rate limit: ~6 req/s, bem dentro do limite de 1000/5min

    print(f"\nResumo: {novos} ofertas criadas | {erros} jogos sem ITAD ID")


if __name__ == "__main__":
    run()
