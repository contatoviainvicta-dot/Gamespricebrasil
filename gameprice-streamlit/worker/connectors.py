"""Conectores de loja para o worker."""
import httpx

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


# ── GOG ───────────────────────────────────────────────────────────────────────

def fetch_gog(external_id: str) -> dict | None:
    """Busca preço na GOG pelo ID do produto.

    Usa o endpoint individual com fallback para o endpoint em lote.
    external_id = ID numérico do produto na GOG (ex: 1207658924)
    """
    # Endpoint 1: individual (mais direto)
    for endpoint in [
        f"https://api.gog.com/products/{external_id}?expand=prices&countryCode=BR",
        f"https://www.gog.com/pt/game/ajax/reviewsPage?gameId={external_id}",
    ]:
        try:
            r = httpx.get(
                endpoint,
                timeout=15,
                headers={
                    "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120",
                    "Accept":          "application/json",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                    "Referer":         "https://www.gog.com/pt/",
                },
                follow_redirects=True,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            prices = data.get("_embedded", {}).get("prices", [])
            if not prices:
                continue
            p = prices[0]
            final = p.get("finalPrice", "0 BRL").split(" ")[0]
            base  = p.get("basePrice",  "0 BRL").split(" ")[0]
            final_val = round(float(final) / 100, 2)
            base_val  = round(float(base)  / 100, 2)
            if final_val <= 0 and base_val <= 0:
                return None
            disc = int(((base_val - final_val) / base_val) * 100) if base_val > 0 else 0
            return {
                "price":            final_val,
                "old_price":        base_val if base_val != final_val else None,
                "discount_percent": disc,
                "available":        True,
            }
        except Exception as exc:
            print(f"  [gog] erro no id {external_id} ({endpoint[:50]}): {exc}")
            continue
    return None


def search_gog(title: str) -> dict | None:
    """Busca um jogo no catálogo da GOG por título.
    Retorna o ID do produto e informações básicas.
    Usado pelo discover_games.py para indexar jogos da GOG.
    """
    try:
        r = httpx.get(
            "https://catalog.gog.com/v1/catalog",
            params={
                "limit":        5,
                "locale":       "pt-BR",
                "countryCode":  "BR",
                "currencyCode": "BRL",
                "productType":  "in:game",
                "query":        f"contains:{title}",
                "order":        "desc:score",
            },
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept":     "application/json",
            },
        )
        r.raise_for_status()
        products = r.json().get("products", [])
    except Exception as exc:
        print(f"  [gog_search] erro para '{title}': {exc}")
        return None

    if not products:
        return None

    p = products[0]
    return {
        "id":    p.get("id", ""),
        "title": p.get("title", ""),
        "slug":  p.get("storeLink", "").replace("/game/", "").strip("/"),
        "cover": p.get("coverHorizontal", ""),
        "price": p.get("price", {}),
    }


# ── Epic Games — Free Games (operante) ───────────────────────────────────────

EPIC_FREE_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=pt-BR&country=BR&allowCountries=BR"
)


def _epic_store_url(el: dict) -> str:
    for m in (el.get("catalogNs") or {}).get("mappings") or []:
        if m.get("pageType") == "productHome" and m.get("pageSlug"):
            return f"https://store.epicgames.com/pt-BR/p/{m['pageSlug']}"
    slug = (el.get("productSlug") or "").replace("/home", "").strip("/")
    if slug and slug != "[]":
        return f"https://store.epicgames.com/pt-BR/p/{slug}"
    slug = el.get("urlSlug") or ""
    if slug:
        return f"https://store.epicgames.com/pt-BR/p/{slug}"
    return "https://store.epicgames.com/pt-BR/free-games"


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
    """Preços da Epic — desativado (endpoint GraphQL mudou)."""
    return None


# ── Mercado Livre (bloqueado por política) ────────────────────────────────────

def fetch_mercadolivre(external_id: str) -> dict | None:
    return None


# ── Amazon (scaffold) ─────────────────────────────────────────────────────────

def fetch_amazon(external_id: str) -> dict | None:
    return None
