"""Worker de atualização de preços + Epic free games.

Roda via GitHub Actions (cron de 6h).
"""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_steam, fetch_epic, fetch_mercadolivre, fetch_amazon
from connectors import fetch_epic_free_games

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

FETCHERS = {
    "steam":        fetch_steam,
    "epic":         fetch_epic,
    "mercadolivre": fetch_mercadolivre,
    "amazon":       fetch_amazon,
}

RATE_LIMITS = {
    "steam":  2.0,
    "epic":   1.0,
    "mercadolivre": 0.8,
    "amazon": 1.0,
}


def sync_epic_free_games(sb) -> None:
    """Sincroniza os jogos gratuitos semanais da Epic com o banco."""
    print("\n=== Epic Games: jogos gratuitos da semana ===")
    data = fetch_epic_free_games()

    current = data.get("current", [])
    nexts   = data.get("next", [])

    print(f"Gratuitos AGORA: {len(current)}")
    for g in current:
        print(f"  🎁 {g['title']} (até {g['end_date'][:10]})")

    print(f"Gratuitos NA PRÓXIMA SEMANA: {len(nexts)}")
    for g in nexts:
        print(f"  🔜 {g['title']} (a partir de {g['start_date'][:10]})")

    # Salva no Supabase como JSON na tabela epic_free_games
    # (criamos a tabela via SQL abaixo)
    payload = {"id": 1, "current": current, "next": nexts}
    try:
        sb.table("epic_free_games").upsert(payload, on_conflict="id").execute()
        print("Epic free games salvo no banco ✓")
    except Exception as e:
        print(f"Erro ao salvar epic free games: {e}")
        print("(Execute o SQL epic_free_games_table.sql no Supabase para criar a tabela)")


def run() -> None:
    sb = create_client(URL, KEY)

    # 1. Sincronizar jogos gratuitos da Epic
    sync_epic_free_games(sb)

    # 2. Atualizar preços de todas as ofertas
    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute()
        .data
    )
    print(f"\n=== Atualização de preços: {len(offers)} ofertas ===")

    rows, erros = [], []
    for i, o in enumerate(offers, 1):
        store_slug = (o.get("stores") or {}).get("slug", "")
        fetcher    = FETCHERS.get(store_slug)
        if fetcher is None:
            continue

        result = fetcher(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(offers)}] OK  {store_slug:<15} "
                  f"{str(o['external_id'])[:35]:<35} "
                  f"R${result['price']:.2f} "
                  f"({result.get('discount_percent', 0)}% off)")
        else:
            erros.append(f"{store_slug}:{str(o['external_id'])[:20]}")
            print(f"  [{i}/{len(offers)}] --- {store_slug:<15} "
                  f"{str(o['external_id'])[:35]} sem preço")

        time.sleep(RATE_LIMITS.get(store_slug, 1.0))

    if rows:
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start + 20]).execute()

    print(f"\nResumo: {len(rows)} preços gravados | {len(erros)} sem resposta")


if __name__ == "__main__":
    run()
