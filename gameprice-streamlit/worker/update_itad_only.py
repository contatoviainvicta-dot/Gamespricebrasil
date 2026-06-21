"""Worker rápido: só ITAD (GOG + Humble) + Epic free games. ~2 minutos."""
import os, sys, time
from supabase import create_client
import httpx

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_epic_free_games

URL       = os.environ["SUPABASE_URL"]
KEY       = os.environ["SUPABASE_SERVICE_KEY"]
ITAD_KEY  = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

ITAD_SHOP_MAP = {35: "gog", 37: "humblestore"}


def itad_prices_lote(itad_ids: list[str], country: str | None = "BR") -> dict:
    params = {"key": ITAD_KEY}
    if country:
        params["country"] = country
    try:
        r = httpx.post(
            f"{ITAD_BASE}/games/prices/v3",
            params=params,
            json=itad_ids,
            headers={"Content-Type": "application/json",
                     "User-Agent": "GamePriceBrasil/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        return {item["id"]: item.get("deals", []) for item in r.json()}
    except Exception as e:
        print(f"  [itad] erro: {e}")
        return {}


def run() -> None:
    sb = create_client(URL, KEY)

    # Epic free games
    print("=== Epic: jogos gratuitos da semana ===")
    data = fetch_epic_free_games()
    current = data.get("current", [])
    nexts   = data.get("next", [])
    print(f"Grátis agora: {len(current)} | Próxima semana: {len(nexts)}")
    for g in current: print(f"  🎁 {g['title']}")
    for g in nexts:   print(f"  🔜 {g['title']}")
    try:
        sb.table("epic_free_games").upsert(
            {"id": 1, "current": current, "next": nexts},
            on_conflict="id"
        ).execute()
        print("Epic free games salvo ✓")
    except Exception as e:
        print(f"Erro: {e}")

    # Buscar ofertas ITAD
    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute().data
    )
    itad_offers = [o for o in offers if o["external_id"].startswith("ITAD|")]
    offer_map   = {o["external_id"]: o["id"] for o in itad_offers}

    print(f"\n=== ITAD (GOG + Humble): {len(itad_offers)} ofertas ===")

    # Diagnóstico no primeiro lote
    primeiro_lote = True
    total = 0
    lote_ext = []

    for i, o in enumerate(itad_offers, 1):
        lote_ext.append(o["external_id"])

        if len(lote_ext) < 20 and i < len(itad_offers):
            continue

        # Extrai ITAD IDs únicos
        seen = set()
        itad_ids = []
        for ext in lote_ext:
            pid = ext.split("|")[2] if ext.count("|") >= 2 else ""
            if pid and pid not in seen:
                itad_ids.append(pid)
                seen.add(pid)

        prices = itad_prices_lote(itad_ids, "BR")
        tem_deals = any(len(v) > 0 for v in prices.values())

        if not tem_deals:
            prices = itad_prices_lote(itad_ids, None)
            tem_deals = any(len(v) > 0 for v in prices.values())

        # Diagnóstico só no primeiro lote
        if primeiro_lote:
            print(f"\n[DIAG] Primeiro lote — {len(itad_ids)} IDs")
            for pid in itad_ids[:3]:
                deals = prices.get(pid, [])
                print(f"  ID={pid[:30]} → {len(deals)} deals")
                for d in deals[:4]:
                    shop  = d.get("shop", {})
                    price = d.get("price", {})
                    print(f"    shop_id={shop.get('id')!r} "
                          f"type={type(shop.get('id')).__name__} "
                          f"name={shop.get('name')} "
                          f"price={price.get('amount')} {price.get('currency')}")
            primeiro_lote = False

        # Processar
        rows = []
        url_updates = {}
        for ext_id in lote_ext:
            parts = ext_id.split("|", 2)
            if len(parts) != 3:
                continue
            _, shop_slug, itad_id = parts
            deals = prices.get(itad_id, [])

            for d in deals:
                shop_id = d.get("shop", {}).get("id")
                # Aceita int ou string
                deal_slug = (ITAD_SHOP_MAP.get(shop_id) or
                             ITAD_SHOP_MAP.get(int(shop_id) if str(shop_id).isdigit() else -1, ""))
                if deal_slug != shop_slug:
                    continue
                amount  = float((d.get("price") or {}).get("amount") or 0)
                regular = float((d.get("regular") or {}).get("amount") or 0)
                cut     = int(d.get("cut") or 0)
                if amount <= 0:
                    continue
                offer_id = offer_map.get(ext_id)
                if not offer_id:
                    continue
                rows.append({
                    "offer_id":         offer_id,
                    "price":            round(amount, 2),
                    "old_price":        round(regular, 2) if regular and regular != amount else None,
                    "discount_percent": cut,
                    "available":        True,
                })
                url_real = d.get("url", "")
                if url_real:
                    url_updates[ext_id] = url_real
                print(f"  OK  {shop_slug:<12} {ext_id[:40]} R${amount:.2f} ({cut}%)")
                break

        if rows:
            for start in range(0, len(rows), 20):
                sb.table("prices").insert(rows[start:start+20]).execute()

        # Atualiza product_url das ofertas com a URL real do deal
        for ext_id, url_real in url_updates.items():
            if url_real and "gog.com" in url_real:
                try:
                    sb.table("game_store_offers")                      .update({"product_url": url_real})                      .eq("external_id", ext_id).execute()
                except Exception:
                    pass

        total += len(rows)
        lote_ext = []
        url_updates = {}
        time.sleep(0.5)

    print(f"\nITAD: {total} preços gravados")


if __name__ == "__main__":
    run()
