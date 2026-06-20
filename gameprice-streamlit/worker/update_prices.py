"""Worker de atualizacao de precos.

Roda via GitHub Actions (cron de 6h).
Usa SUPABASE_SERVICE_KEY para gravar ignorando o RLS.
"""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_steam, fetch_mercadolivre, fetch_amazon

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

FETCHERS = {
    "steam":         fetch_steam,
    "mercadolivre":  fetch_mercadolivre,
    "amazon":        fetch_amazon,
}

# Rate limits por loja (segundos entre requisicoes)
RATE_LIMITS = {
    "steam":        1.2,
    "mercadolivre": 0.5,
    "amazon":       1.0,
}


def run() -> None:
    sb = create_client(URL, KEY)

    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute()
        .data
    )
    print(f"{len(offers)} ofertas ativas para atualizar")

    rows, erros = [], []
    for i, o in enumerate(offers, 1):
        store_slug = (o.get("stores") or {}).get("slug", "")
        fetcher    = FETCHERS.get(store_slug)
        if fetcher is None:
            continue

        result = fetcher(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(offers)}] OK  {store_slug} "
                  f"ext={o['external_id'][:30]} "
                  f"R${result['price']:.2f} "
                  f"({result.get('discount_percent',0)}% off)")
        else:
            erros.append(f"{store_slug}:{o['external_id'][:20]}")
            print(f"  [{i}/{len(offers)}] --- {store_slug} "
                  f"ext={o['external_id'][:30]} sem preco")

        sleep = RATE_LIMITS.get(store_slug, 1.0)
        time.sleep(sleep)

    if rows:
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start+20]).execute()

    print(f"\nResumo: {len(rows)} precos gravados | {len(erros)} sem resposta")
    if erros:
        print(f"Sem preco: {erros[:10]}")


if __name__ == "__main__":
    run()
