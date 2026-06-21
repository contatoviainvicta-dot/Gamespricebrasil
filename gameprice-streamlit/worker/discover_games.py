"""Descoberta automática de jogos via SteamSpy + Steam Featured.

Roda junto com o worker de preços (GitHub Actions).
Adiciona automaticamente ao banco jogos que:
  1. Estão entre os top 100 mais jogados (SteamSpy)
  2. Estão em promoção destaque na Steam (Steam Featured)
  3. São lançamentos recentes populares

Não requer nenhuma credencial — APIs públicas.
"""
import os
import time
import httpx
from slugify import slugify
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def steam_slug(title: str) -> str:
    return slugify(f"{title}-pc")


def fetch_steamspy_top() -> list[dict]:
    """Busca top 100 jogos por jogadores nas últimas 2 semanas."""
    try:
        r = httpx.get(
            "https://steamspy.com/api.php",
            params={"request": "top100in2weeks"},
            timeout=20,
            headers={"User-Agent": "GamePriceBrasil/1.0"},
        )
        r.raise_for_status()
        data = r.json()
        return [
            {"appid": str(appid), "title": info.get("name", "")}
            for appid, info in data.items()
            if info.get("name")
        ]
    except Exception as e:
        print(f"  [steamspy] erro: {e}")
        return []


def fetch_steam_featured() -> list[dict]:
    """Busca jogos em destaque/promoção na Steam Brasil."""
    jogos = []
    try:
        r = httpx.get(
            "https://store.steampowered.com/api/featuredcategories",
            params={"cc": "br", "l": "portuguese"},
            timeout=20,
            headers={"User-Agent": "GamePriceBrasil/1.0"},
        )
        r.raise_for_status()
        data = r.json()

        # Categorias com jogos em destaque
        categorias = [
            "specials",          # promoções
            "top_sellers",       # mais vendidos
            "new_releases",      # lançamentos
            "coming_soon",       # em breve
        ]
        for cat in categorias:
            items = data.get(cat, {}).get("items", [])
            for item in items:
                appid = str(item.get("id", ""))
                title = item.get("name", "")
                if appid and title:
                    jogos.append({"appid": appid, "title": title})
    except Exception as e:
        print(f"  [steam_featured] erro: {e}")
    return jogos


def fetch_steam_top_sellers() -> list[dict]:
    """Busca top sellers globais via Steam Store."""
    jogos = []
    try:
        r = httpx.get(
            "https://store.steampowered.com/api/featuredcategories",
            params={"cc": "br", "l": "portuguese"},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("top_sellers", {}).get("items", [])
        for item in items:
            if item.get("id") and item.get("name"):
                jogos.append({
                    "appid": str(item["id"]),
                    "title": item["name"],
                })
    except Exception as e:
        print(f"  [top_sellers] erro: {e}")
    return jogos


def adicionar_jogos_novos(sb, candidatos: list[dict]) -> int:
    """Adiciona jogos que ainda não estão no banco. Retorna quantos foram adicionados."""
    if not candidatos:
        return 0

    # Busca appids já existentes no banco
    ofertas_existentes = (
        sb.table("game_store_offers")
        .select("external_id")
        .execute()
        .data
    )
    appids_existentes = {o["external_id"] for o in ofertas_existentes}

    # Busca a store Steam
    store = sb.table("stores").select("id").eq("slug", "steam").execute().data
    if not store:
        print("  [discover] loja Steam não encontrada no banco")
        return 0
    store_id = store[0]["id"]

    novos = 0
    for c in candidatos:
        appid = c["appid"]
        title = c["title"]

        if not appid or not title or appid in appids_existentes:
            continue

        slug = steam_slug(title)

        try:
            # Insere o jogo (ignora se slug já existe)
            result = sb.table("games").upsert(
                {
                    "title":     title,
                    "slug":      slug,
                    "platform":  "PC",
                    "cover_url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                },
                on_conflict="slug",
            ).execute()

            game_id = result.data[0]["id"] if result.data else None
            if not game_id:
                # Busca o id pelo slug
                g = sb.table("games").select("id").eq("slug", slug).execute().data
                game_id = g[0]["id"] if g else None

            if game_id:
                sb.table("game_store_offers").upsert(
                    {
                        "game_id":     game_id,
                        "store_id":    store_id,
                        "external_id": appid,
                        "product_url": f"https://store.steampowered.com/app/{appid}/",
                    },
                    on_conflict="store_id,external_id",
                ).execute()
                appids_existentes.add(appid)
                novos += 1
                print(f"  [discover] +novo: {title} (appid={appid})")
        except Exception as e:
            print(f"  [discover] erro ao inserir {title}: {e}")

        time.sleep(0.1)

    return novos


def run() -> None:
    sb = create_client(URL, KEY)
    print("=== Descoberta de novos jogos ===")

    candidatos: list[dict] = []

    print("Buscando SteamSpy top 100...")
    candidatos += fetch_steamspy_top()
    time.sleep(2)

    print("Buscando Steam Featured/Promoções...")
    candidatos += fetch_steam_featured()
    time.sleep(1)

    # Deduplica por appid
    vistos: set = set()
    unicos = []
    for c in candidatos:
        if c["appid"] not in vistos:
            vistos.add(c["appid"])
            unicos.append(c)

    print(f"{len(unicos)} candidatos únicos encontrados")
    novos = adicionar_jogos_novos(sb, unicos)
    print(f"=== {novos} jogos novos adicionados ao catálogo ===")


if __name__ == "__main__":
    run()
