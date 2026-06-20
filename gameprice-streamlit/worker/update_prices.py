"""Worker de atualização de preços.

Roda via GitHub Actions (cron de 6h).
Usa SUPABASE_SERVICE_KEY para gravar ignorando o RLS.
Respeita rate limit da Steam: 1 req/s com pausa entre chamadas.
"""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_steam, fetch_mercadolivre  # noqa: E402

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

FETCHERS = {
    "steam":        fetch_steam,
    "mercadolivre": fetch_mercadolivre,
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
        fetcher = FETCHERS.get(store_slug)
        if fetcher is None:
            continue

        result = fetcher(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(offers)}] OK  appid={o['external_id']} "
                  f"R${result['price']:.2f} ({result.get('discount_percent',0)}% off)")
        else:
            erros.append(o["external_id"])
            print(f"  [{i}/{len(offers)}] --- appid={o['external_id']} sem preço")

        # Rate limit: máx ~1 req/s na Steam
        if store_slug == "steam":
            time.sleep(1.2)

    if rows:
        # Inserir em lotes de 20 para não estourar o payload do Supabase
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start+20]).execute()

    print(f"\nResumo: {len(rows)} preços gravados | {len(erros)} sem resposta")
    if erros:
        print(f"Sem preço: {erros}")

if __name__ == "__main__":
    run()
