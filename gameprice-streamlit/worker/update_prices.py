"""Worker de atualizacao de precos.

Roda no GitHub Actions (cron de 6h) ou localmente. Usa a chave SERVICE_ROLE
do Supabase, que ignora o RLS para poder gravar precos.
"""
import os
import sys

from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_mercadolivre, fetch_steam  # noqa: E402

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

FETCHERS = {"steam": fetch_steam, "mercadolivre": fetch_mercadolivre}


def run() -> None:
    sb = create_client(URL, KEY)
    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute()
        .data
    )
    print(f"{len(offers)} ofertas ativas")

    rows = []
    for o in offers:
        slug = (o.get("stores") or {}).get("slug")
        fetcher = FETCHERS.get(slug)
        if fetcher is None:
            continue
        result = fetcher(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})

    if rows:
        sb.table("prices").insert(rows).execute()
    print(f"{len(rows)} precos novos gravados")


if __name__ == "__main__":
    run()
