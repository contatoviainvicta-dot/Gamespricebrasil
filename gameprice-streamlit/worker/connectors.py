"""Conectores de loja para o worker."""
import os
import httpx

ITAD_KEY  = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

# ITAD shop_id (inteiro) → slug interno do banco
# Descobertos via diagnóstico: GOG=35, Steam=61, Humble=37
ITAD_SHOP_ID_MAP: dict[int, str] = {
    35: "gog",
    37: "humblestore",
}


# ── Steam ─────────────────────────────────────────────────────────────────────

def fetch_steam(appid: str, cc: str = "br", lang: str = "portuguese") -> dict | None:
    try:
        r = httpx.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "cc": cc, "l": lang, "filters": "price_overview"},
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        raw = r.json().get(str(appid), {})
    except Exception as exc:
        print(f"  [steam] erro no appid {appid}: {exc}")
        return None

    if not raw.get("success"):
        return None

    data = raw.get("data", {})
    if isinstance(data, list):
        data = data[0] if data else {}

    po = data.get("price_overview") if isinstance(data, dict) else None

    if po is None:
        return {"price": 0.0, "old_price": None, "discount_percent": 0, "available": True}

    return {
        "price":            round(po["final"] / 100, 2),
        "old_price":        round(po["initial"] / 100, 2) if po.get("initial") else None,
        "discount_percent": po.get("discount_percent", 0),
        "available":        True,
    }


# ── ITAD (GOG, Humble Store, etc.) ───────────────────────────────────────────

def _itad_prices_batch(itad_ids: list[str], country: str = "BR") -> dict:
    """Busca preços em lote via ITAD. Retorna {itad_id: [deals]}."""
    if not itad_ids or not ITAD_KEY:
        return {}
    try:
        r = httpx.post(
            f"{ITAD_BASE}/games/prices/v3",
            params={"key": ITAD_KEY, "country": country},
            json=itad_ids,
            headers={"Content-Type": "application/json",
                     "User-Agent": "GamePriceBrasil/1.0"},
            timeout=20,
        )
        r.raise_for_status()
        return {item["id"]: item.get("deals", []) for item in r.json()}
    except Exception as exc:
        print(f"  [itad] batch error: {exc}")
        return {}


def fetch_itad(external_id: str) -> dict | None:
    """Busca preço via ITAD.

    external_id formato: ITAD|SHOP_SLUG|ITAD_GAME_ID
    ex: ITAD|gog|018d937f-1212-7232-b23f-a046f6fd4a57
    """
    if not external_id.startswith("ITAD|"):
        return None
    parts = external_id.split("|", 2)
    if len(parts) != 3:
        return None
    _, shop_slug, itad_id = parts

    prices = _itad_prices_batch([itad_id])
    deals  = prices.get(itad_id, [])

    for d in deals:
        shop_id_num = d.get("shop", {}).get("id")      # inteiro
        deal_slug   = ITAD_SHOP_ID_MAP.get(shop_id_num, "")
        if deal_slug == shop_slug:
            amount  = (d.get("price") or {}).get("amount", 0)
            regular = (d.get("regular") or {}).get("amount", 0)
            cut     = d.get("cut", 0)
            return {
                "price":            round(float(amount), 2),
                "old_price":        round(float(regular), 2) if regular and regular != amount else None,
                "discount_percent": int(cut),
                "available":        True,
            }
    return None


def fetch_gog(external_id: str) -> dict | None:
    """Dispatcher para GOG.

    Aceita dois formatos:
    - ITAD|gog|UUID  → busca via ITAD (novo formato)
    - ID_NUMERICO    → busca direto na API GOG (legado, pode falhar)
    """
    if external_id.startswith("ITAD|gog|"):
        return fetch_itad(external_id)

    # Legado: ID numérico inserido manualmente
    # Tenta via ITAD usando lookup reverso
    if not ITAD_KEY:
        return None
    try:
        # Busca o produto GOG pelo ID numérico via api.gog.com
        r = httpx.get(
            f"https://api.gog.com/products/{external_id}",
            params={"expand": "prices", "countryCode": "BR"},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                     "AppleWebKit/537.36 Chrome/120"},
            timeout=15,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        data   = r.json()
        prices = data.get("_embedded", {}).get("prices", [])
        if not prices:
            return None
        p     = prices[0]
        final = float(p.get("finalPrice", "0 BRL").split()[0]) / 100
        base  = float(p.get("basePrice",  "0 BRL").split()[0]) / 100
        if final <= 0:
            return None
        disc = int(((base - final) / base) * 100) if base > 0 else 0
        return {
            "price":            round(final, 2),
            "old_price":        round(base, 2) if base != final else None,
            "discount_percent": disc,
            "available":        True,
        }
    except Exception as exc:
        print(f"  [gog_legacy] {external_id}: {exc}")
        return None


def fetch_humblestore(external_id: str) -> dict | None:
    """Humble Store via ITAD."""
    if external_id.startswith("ITAD|humblestore|"):
        return fetch_itad(external_id)
    return None


# ── Epic Games — Free Games (sem auth, sempre funciona) ───────────────────────

EPIC_FREE_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=pt-BR&country=BR&allowCountries=BR"
)


def fetch_epic_free_games() -> dict:
    """Retorna jogos gratuitos AGORA e PRÓXIMA SEMANA na Epic."""
    result = {"current": [], "next": []}
    try:
        r = httpx.get(EPIC_FREE_URL, timeout=20,
                      headers={"User-Agent": "Mozilla/5.0",
                               "Accept": "application/json"},
                      follow_redirects=True)
        r.raise_for_status()
        elements = r.json()["data"]["Catalog"]["searchStore"]["elements"]
    except Exception as exc:
        print(f"  [epic_free] erro: {exc}")
        return result

    for el in elements:
        title  = el.get("title", "")
        promos = el.get("promotions") or {}
        imgs   = el.get("keyImages", [])
        image_url = ""
        for tipo in ["Thumbnail","DieselStoreFrontWide","OfferImageWide"]:
            img = next((i["url"] for i in imgs if i.get("type") == tipo), None)
            if img:
                image_url = img
                break
        store_url = "https://store.epicgames.com/pt-BR/free-games"

        for grp in promos.get("promotionalOffers", []):
            for offer in grp.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["current"].append({
                        "title": title, "image_url": image_url,
                        "end_date": offer.get("endDate", ""),
                        "store_url": store_url,
                    })
        for grp in promos.get("upcomingPromotionalOffers", []):
            for offer in grp.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["next"].append({
                        "title": title, "image_url": image_url,
                        "start_date": offer.get("startDate", ""),
                        "store_url": store_url,
                    })
    return result


def fetch_epic(external_id: str) -> dict | None:
    """Preços Epic via ITAD."""
    if external_id.startswith("ITAD|epic|"):
        return fetch_itad(external_id)
    return None


# ── Mercado Livre / Amazon (scaffold) ─────────────────────────────────────────

def fetch_mercadolivre(external_id: str) -> dict | None:
    return None

def fetch_amazon(external_id: str) -> dict | None:
    return None
