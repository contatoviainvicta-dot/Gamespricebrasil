"""Conectores de loja para o worker.

Steam  : API pública de storefront. Operante.
ITAD   : IsThereAnyDeal API — agrega GOG, Epic, Nuuvem, Fanatical e 30+ lojas.
Epic   : Free Games semanais (endpoint separado, sem autenticação).
ML/Amazon: scaffold.
"""
import os
import time
import httpx

ITAD_KEY = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

# Lojas do ITAD que queremos cobrir (slugs da ITAD)
ITAD_SHOPS = ["gog", "epic", "nuuvem", "fanatical", "humblestore", "greenmanrepublic"]


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


# ── IsThereAnyDeal ────────────────────────────────────────────────────────────

# Cache em memória: título → ITAD ID (evita buscas repetidas)
_itad_id_cache: dict[str, str] = {}


def itad_lookup_by_title(title: str) -> str | None:
    """Busca o ITAD ID de um jogo pelo título."""
    if title in _itad_id_cache:
        return _itad_id_cache[title]
    try:
        r = httpx.get(
            f"{ITAD_BASE}/games/search/v1",
            params={"title": title, "key": ITAD_KEY},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()
        if results:
            itad_id = results[0]["id"]
            _itad_id_cache[title] = itad_id
            return itad_id
    except Exception as exc:
        print(f"  [itad] lookup '{title}': {exc}")
    return None


def itad_prices_batch(itad_ids: list[str], country: str = "BR") -> dict[str, list]:
    """Busca preços de múltiplos jogos em lote.
    Retorna {itad_id: [{"shop": "gog", "price": 12.99, "cut": 90, "url": ...}]}
    """
    if not itad_ids or not ITAD_KEY:
        return {}
    try:
        r = httpx.post(
            f"{ITAD_BASE}/games/prices/v3",
            params={"key": ITAD_KEY, "country": country},
            json=itad_ids,
            headers={
                "Content-Type": "application/json",
                "User-Agent":   "GamePriceBrasil/1.0",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"  [itad] prices_batch: {exc}")
        return {}

    result = {}
    for item in data:
        gid   = item.get("id", "")
        deals = item.get("deals", [])
        prices_list = []
        for d in deals:
            shop_slug = d.get("shop", {}).get("id", "")
            amount    = (d.get("price") or {}).get("amount", 0)
            regular   = (d.get("regular") or {}).get("amount", 0)
            cut       = d.get("cut", 0)
            url       = d.get("url", "")
            if amount and amount > 0:
                prices_list.append({
                    "shop":     shop_slug,
                    "price":    round(float(amount), 2),
                    "old_price": round(float(regular), 2) if regular and regular != amount else None,
                    "cut":      int(cut),
                    "url":      url,
                })
        result[gid] = prices_list
    return result


def fetch_itad(external_id: str) -> dict | None:
    """Busca preço via ITAD para GOG, Epic ou outra loja.

    external_id formato: ITAD|SHOP_SLUG|ITAD_GAME_ID
    ex: ITAD|gog|018d937f-590e-7271-8e31-e0e4e9e8c5ed
    """
    if not external_id.startswith("ITAD|"):
        return None
    parts = external_id.split("|", 2)
    if len(parts) != 3:
        return None
    _, shop_slug, itad_id = parts

    prices = itad_prices_batch([itad_id])
    deals  = prices.get(itad_id, [])

    # Filtra pelo shop correto
    for d in deals:
        if d["shop"] == shop_slug:
            return {
                "price":            d["price"],
                "old_price":        d.get("old_price"),
                "discount_percent": d["cut"],
                "available":        True,
            }
    return None


# ── Epic Games — Free Games (operante, sem auth) ──────────────────────────────

EPIC_FREE_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=pt-BR&country=BR&allowCountries=BR"
)


def fetch_epic_free_games() -> dict:
    """Retorna jogos gratuitos AGORA e PRÓXIMA SEMANA na Epic."""
    result = {"current": [], "next": []}
    try:
        r = httpx.get(
            EPIC_FREE_URL,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept":     "application/json",
            },
            follow_redirects=True,
        )
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
        for tipo in ["Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultOpened"]:
            img = next((i["url"] for i in imgs if i.get("type") == tipo), None)
            if img:
                image_url = img
                break

        store_url = "https://store.epicgames.com/pt-BR/free-games"

        for grp in promos.get("promotionalOffers", []):
            for offer in grp.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["current"].append({
                        "title":     title,
                        "image_url": image_url,
                        "end_date":  offer.get("endDate", ""),
                        "store_url": store_url,
                    })

        for grp in promos.get("upcomingPromotionalOffers", []):
            for offer in grp.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["next"].append({
                        "title":      title,
                        "image_url":  image_url,
                        "start_date": offer.get("startDate", ""),
                        "store_url":  store_url,
                    })
    return result


def fetch_epic(external_id: str) -> dict | None:
    """Preços Epic via ITAD (se external_id começa com ITAD|epic|...)."""
    if external_id.startswith("ITAD|epic|"):
        return fetch_itad(external_id)
    return None


def fetch_gog(external_id: str) -> dict | None:
    """Preços GOG via ITAD (se external_id começa com ITAD|gog|...)."""
    if external_id.startswith("ITAD|"):
        return fetch_itad(external_id)
    # ID numérico legado (inserido manualmente) — sem fetch automático
    return None


# ── Mercado Livre / Amazon (scaffold) ─────────────────────────────────────────

def fetch_mercadolivre(external_id: str) -> dict | None:
    return None


def fetch_amazon(external_id: str) -> dict | None:
    return None
