"""Worker de atualização de preços — Steam individual + ITAD em lote."""
import os, sys, time
from supabase import create_client
import httpx

sys.path.insert(0, os.path.dirname(__file__))
from connectors import fetch_steam, fetch_epic_free_games

URL       = os.environ["SUPABASE_URL"]
KEY       = os.environ["SUPABASE_SERVICE_KEY"]
ITAD_KEY  = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

ITAD_SHOP_MAP = {35: "gog", 37: "humblestore"}


def itad_prices_lote(itad_ids: list[str], country: str | None = "BR") -> dict:
    if not itad_ids or not ITAD_KEY:
        return {}
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
        print(f"  [itad] lote erro (country={country}): {e}")
        return {}


def processar_itad(sb, lote_ext: list[str], offer_map: dict,
                   diagnostico: bool = False) -> int:
    if not lote_ext:
        return 0

    # Extrai ITAD IDs únicos
    itad_ids = []
    seen = set()
    for ext in lote_ext:
        if ext.startswith("ITAD|"):
            parts = ext.split("|", 2)
            if len(parts) == 3 and parts[2] not in seen:
                itad_ids.append(parts[2])
                seen.add(parts[2])

    if not itad_ids:
        return 0

    # Tenta com BR primeiro, depois sem country
    prices = itad_prices_lote(itad_ids, "BR")
    tem_deals = any(len(v) > 0 for v in prices.values())

    if not tem_deals:
        print(f"  [itad] country=BR sem deals, tentando sem country...")
        prices = itad_prices_lote(itad_ids, None)
        tem_deals = any(len(v) > 0 for v in prices.values())

    if diagnostico and itad_ids:
        # Mostra o que o ITAD retornou para o primeiro ID
        primeiro_id = itad_ids[0]
        deals = prices.get(primeiro_id, [])
        print(f"  [DIAG] ID={primeiro_id} → {len(deals)} deals")
        for d in deals[:5]:
            shop = d.get("shop", {})
            price = d.get("price", {})
            print(f"    shop_id={shop.get('id')} ({type(shop.get('id')).__name__}) "
                  f"name={shop.get('name')} "
                  f"price={price.get('amount')} {price.get('currency')}")

    rows = []
    for ext_id in lote_ext:
        if not ext_id.startswith("ITAD|"):
            continue
        parts = ext_id.split("|", 2)
        if len(parts) != 3:
            continue
        _, shop_slug, itad_id = parts

        deals = prices.get(itad_id, [])
        for d in deals:
            shop_raw    = d.get("shop", {})
            shop_id_num = shop_raw.get("id")

            # Tenta int e string
            slug_por_int = ITAD_SHOP_MAP.get(shop_id_num, "")
            slug_por_str = ITAD_SHOP_MAP.get(str(shop_id_num), "")
            deal_slug    = slug_por_int or slug_por_str

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
            print(f"  OK  {shop_slug:<12} {ext_id[:45]:<45} "
                  f"R${amount:.2f} ({cut}% off)")
            break

    if rows:
        for start in range(0, len(rows), 20):
            sb.table("prices").insert(rows[start:start+20]).execute()

    return len(rows)


def sync_epic_free_games(sb) -> None:
    print("\n=== Epic: jogos gratuitos da semana ===")
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


def run() -> None:
    sb = create_client(URL, KEY)
    sync_epic_free_games(sb)

    offers = (
        sb.table("game_store_offers")
        .select("id, external_id, stores(slug)")
        .eq("active", True)
        .execute().data
    )
    print(f"\n=== Preços: {len(offers)} ofertas ===")

    steam_offers = []
    itad_offers  = []

    for o in offers:
        slug = (o.get("stores") or {}).get("slug", "")
        eid  = o["external_id"]
        if slug == "steam":
            steam_offers.append(o)
        elif eid.startswith("ITAD|"):
            itad_offers.append(o)

    # ── Steam ─────────────────────────────────────────────────────────────────
    print(f"\n--- Steam: {len(steam_offers)} ofertas ---")
    steam_rows = []
    for i, o in enumerate(steam_offers, 1):
        result = fetch_steam(o["external_id"])
        if result:
            steam_rows.append({"offer_id": o["id"], **result})
            print(f"  [{i}/{len(steam_offers)}] OK  steam "
                  f"{o['external_id']:<12} "
                  f"R${result['price']:.2f} ({result.get('discount_percent',0)}% off)")
        else:
            print(f"  [{i}/{len(steam_offers)}] --- steam "
                  f"{o['external_id']} sem preço")
        time.sleep(2.0)

    if steam_rows:
        for start in range(0, len(steam_rows), 20):
            sb.table("prices").insert(steam_rows[start:start+20]).execute()
    print(f"Steam: {len(steam_rows)} preços gravados")

    # ── ITAD em lote ──────────────────────────────────────────────────────────
    print(f"\n--- ITAD (GOG + Humble): {len(itad_offers)} ofertas ---")
    offer_map = {o["external_id"]: o["id"] for o in itad_offers}

    total_itad = 0
    lote_ext   = []
    primeiro_lote = True

    for i, o in enumerate(itad_offers, 1):
        lote_ext.append(o["external_id"])

        if len(lote_ext) >= 20 or i == len(itad_offers):
            n = processar_itad(sb, lote_ext, offer_map,
                               diagnostico=primeiro_lote)
            total_itad   += n
            lote_ext      = []
            primeiro_lote = False
            time.sleep(0.5)

    print(f"ITAD: {total_itad} preços gravados")
    print(f"\nResumo total: {len(steam_rows) + total_itad} preços gravados")


if __name__ == "__main__":
    run()
