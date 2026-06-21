"""Descoberta contínua de novos jogos via SteamSpy + Steam Featured.
Roda a cada ciclo do update-prices (6h).
Adiciona jogos que aparecem nos rankings mas ainda não estão no banco.
"""
import os, sys, time
import httpx
from slugify import slugify
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def fetch_steamspy_top() -> list[dict]:
    """Top 100 mais jogados na quinzena."""
    try:
        r = httpx.get(
            "https://steamspy.com/api.php",
            params={"request": "top100in2weeks"},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=20,
        )
        r.raise_for_status()
        return [{"appid": str(k), "title": v.get("name","")}
                for k, v in r.json().items() if v.get("name")]
    except Exception as e:
        print(f"  [steamspy_top] erro: {e}")
        return []


def fetch_steam_featured() -> list[dict]:
    """Destaques e promoções da Steam."""
    jogos = []
    try:
        r = httpx.get(
            "https://store.steampowered.com/api/featuredcategories",
            params={"cc": "br", "l": "portuguese"},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        for cat in ["specials", "top_sellers", "new_releases"]:
            for item in data.get(cat, {}).get("items", []):
                if item.get("id") and item.get("name"):
                    jogos.append({"appid": str(item["id"]), "title": item["name"]})
    except Exception as e:
        print(f"  [steam_featured] erro: {e}")
    return jogos


def fetch_steamspy_page0() -> list[dict]:
    """Página 0 do SteamSpy — top 1000 mais populares."""
    try:
        r = httpx.get(
            "https://steamspy.com/api.php",
            params={"request": "all", "page": 0},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        return [{"appid": str(k), "title": v.get("name","")}
                for k, v in r.json().items() if v.get("name")]
    except Exception as e:
        print(f"  [steamspy_all] erro: {e}")
        return []


def run() -> None:
    sb = create_client(URL, KEY)
    print("=== Descoberta de jogos ===")

    # Coletar candidatos de múltiplas fontes
    candidatos = []
    print("Buscando SteamSpy top 100...")
    candidatos += fetch_steamspy_top()
    time.sleep(1.5)

    print("Buscando Steam Featured...")
    candidatos += fetch_steam_featured()
    time.sleep(1)

    print("Buscando SteamSpy top 1000...")
    candidatos += fetch_steamspy_page0()
    time.sleep(1.5)

    # Deduplicar por appid
    vistos: set = set()
    unicos = []
    for c in candidatos:
        if c["appid"] not in vistos and c["title"]:
            vistos.add(c["appid"])
            unicos.append(c)
    print(f"{len(unicos)} candidatos únicos")

    # Buscar o que já existe
    existentes = {
        o["external_id"]
        for o in sb.table("game_store_offers").select("external_id").execute().data
    }
    steam = sb.table("stores").select("id").eq("slug","steam").execute().data
    if not steam:
        return
    steam_id = steam[0]["id"]

    novos = [c for c in unicos if c["appid"] not in existentes]
    print(f"{len(novos)} jogos novos para adicionar")

    inseridos = 0
    for c in novos:
        slug = slugify(f"{c['title']}-pc")
        try:
            r = sb.table("games").upsert(
                {"title": c["title"], "slug": slug, "platform": "PC",
                 "cover_url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{c['appid']}/header.jpg"},
                on_conflict="slug"
            ).execute()
            game_id = r.data[0]["id"] if r.data else None
            if not game_id:
                g = sb.table("games").select("id").eq("slug", slug).execute().data
                game_id = g[0]["id"] if g else None
            if game_id:
                sb.table("game_store_offers").upsert(
                    {"game_id": game_id, "store_id": steam_id,
                     "external_id": c["appid"],
                     "product_url": f"https://store.steampowered.com/app/{c['appid']}/",
                     "active": True},
                    on_conflict="store_id,external_id"
                ).execute()
                existentes.add(c["appid"])
                inseridos += 1
                print(f"  + {c['title'][:50]} (appid={c['appid']})")
        except Exception as e:
            print(f"  Erro {c['title']}: {e}")
        time.sleep(0.1)

    total = len(sb.table("games").select("id").execute().data)
    print(f"=== {inseridos} novos | {total} jogos no banco ===")


if __name__ == "__main__":
    run()
