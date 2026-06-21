"""Worker de atualização de preços + Epic free games + GOG."""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import (
    fetch_steam, fetch_gog, fetch_epic, fetch_mercadolivre, fetch_amazon,
    fetch_epic_free_games,
)

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

FETCHERS = {
    "steam":        fetch_steam,
    "gog":          fetch_gog,
    "epic":         fetch_epic,
    "mercadolivre": fetch_mercadolivre,
    "amazon":       fetch_amazon,
}

RATE_LIMITS = {
    "steam": 2.0,
    "gog":   0.3,   # 4 req/s permitido
    "epic":  1.0,
    "mercadolivre": 0.8,
    "amazon": 1.0,
}


def sync_epic_free_games(sb) -> None:
    print("\n=== Epic: jogos gratuitos da semana ===")
    data = fetch_epic_free_games()
    current = data.get("current", [])
    nexts   = data.get("next", [])
    print(f"Grátis agora: {len(current)} | Próxima semana: {len(nexts)}")
    for g in current:
        print(f"  🎁 {g['title']}")
    for g in nexts:
        print(f"  🔜 {g['title']}")
    try:
        sb.table("epic_free_games").upsert(
            {"id": 1, "current": current, "next": nexts},
            on_conflict="id"
        ).execute()
        print("Epic free games salvo ✓")
    except Exception as e:
        print(f"Erro ao salvar epic free games: {e}")


def run() -> None:
    sb = create_client(URL, KEY)

    sync_epic_free_games(sb)

    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute()
        .data
    )
    print(f"\n=== Preços: {len(offers)} ofertas ===")

    rows, erros = [], []
    for i, o in enumerate(offers, 1):
        store_slug = (o.get("stores") or {}).get("slug", "")
        fetcher    = FETCHERS.get(store_slug)
        if fetcher is None:
            continue

        result = fetcher(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(offers)}] OK  {store_slug:<8} "
                  f"{str(o['external_id'])[:30]:<30} "
                  f"R${result['price']:.2f} ({result.get('discount_percent',0)}% off)")
        else:
            erros.append(f"{store_slug}:{str(o['external_id'])[:20]}")
            print(f"  [{i}/{len(offers)}] --- {store_slug:<8} "
                  f"{str(o['external_id'])[:30]} sem preço")

        time.sleep(RATE_LIMITS.get(store_slug, 1.0))

    if rows:
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start+20]).execute()

    print(f"\nResumo: {len(rows)} preços gravados | {len(erros)} sem resposta")


if __name__ == "__main__":
    run()
