"""Worker de preços Steam — roda a cada 6h via GitHub Actions."""
import os, sys, time
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_steam

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def run() -> None:
    sb = create_client(URL, KEY)

    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute().data
    )

    steam_offers = [o for o in offers
                    if (o.get("stores") or {}).get("slug") == "steam"]
    print(f"=== Steam: {len(steam_offers)} ofertas ===")

    rows = []
    for i, o in enumerate(steam_offers, 1):
        result = fetch_steam(o["external_id"])
        if result:
            rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(steam_offers)}] OK  "
                  f"{o['external_id']:<12} "
                  f"R${result['price']:.2f} ({result.get('discount_percent',0)}% off)")
        else:
            print(f"  [{i}/{len(steam_offers)}] --- "
                  f"{o['external_id']} sem preço")
        time.sleep(2.0)

    if rows:
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start+20]).execute()

    print(f"\nSteam: {len(rows)} preços gravados")


if __name__ == "__main__":
    run()
