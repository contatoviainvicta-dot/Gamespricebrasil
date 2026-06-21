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


# ── Epic Games — Free Games (operante) ───────────────────────────────────────

EPIC_FREE_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=pt-BR&country=BR&allowCountries=BR"
)


def _epic_store_url(el: dict) -> str:
    """Monta a URL correta da Epic a partir do elemento da API."""
    # 1. catalogNs.mappings → mais confiável
    for m in (el.get("catalogNs") or {}).get("mappings") or []:
        if m.get("pageType") == "productHome" and m.get("pageSlug"):
            return f"https://store.epicgames.com/pt-BR/p/{m['pageSlug']}"

    # 2. productSlug
    slug = (el.get("productSlug") or "").replace("/home", "").strip("/")
    if slug and slug != "[]":
        return f"https://store.epicgames.com/pt-BR/p/{slug}"

    # 3. urlSlug
    slug = el.get("urlSlug") or ""
    if slug:
        return f"https://store.epicgames.com/pt-BR/p/{slug}"

    # 4. Fallback
    return "https://store.epicgames.com/pt-BR/free-games"


def fetch_epic_free_games() -> dict:
    """Retorna jogos gratuitos AGORA e PRÓXIMA SEMANA na Epic.
    
    Este endpoint é estável e funciona sem autenticação.
    """
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

        store_url = _epic_store_url(el)

        # Gratuito AGORA
        for grp in promos.get("promotionalOffers", []):
            for offer in grp.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["current"].append({
                        "title":     title,
                        "image_url": image_url,
                        "end_date":  offer.get("endDate", ""),
                        "store_url": store_url,
                    })

        # Gratuito PRÓXIMA SEMANA
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


# ── Epic Games — Preços (endpoint GraphQL mudou — desativado temporariamente) ─

def fetch_epic(external_id: str) -> dict | None:
    """Preços da Epic via GraphQL.
    
    O endpoint graphql.epicgames.com foi descontinuado (retorna 404).
    O novo endpoint store.epicgames.com/graphql ainda está sendo validado.
    Desativado temporariamente — jogos gratuitos semanais continuam funcionando.
    """
    return None


# ── Mercado Livre (bloqueado por política — aguardando afiliados) ─────────────

def fetch_mercadolivre(external_id: str) -> dict | None:
    """Bloqueado por política da API (403 de IPs de datacenter).
    Aguardando aprovação no programa de afiliados.
    """
    return None


# ── Amazon (scaffold) ─────────────────────────────────────────────────────────

def fetch_amazon(external_id: str) -> dict | None:
    """Scaffold: precisa de conta Amazon Associates + PA-API 5.0."""
    return None
