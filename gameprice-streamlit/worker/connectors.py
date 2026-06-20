"""Conectores de loja para o worker.

Steam  : API publica de storefront. Operante.
ML     : API publica de busca (sem token). Operante.
Amazon : Scaffold.
"""
import httpx


# ── Steam ─────────────────────────────────────────────────────────────────────

def fetch_steam(appid: str, cc: str = "br", lang: str = "portuguese") -> dict | None:
    """Retorna preco atual de um jogo na Steam pelo appid."""
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


# ── Mercado Livre ─────────────────────────────────────────────────────────────

ML_CATEGORIAS = {
    "PS5":    "MLB1132",
    "PS4":    "MLB1133",
    "XBOX":   "MLB1069",
    "SWITCH": "MLB1131",
    "PC":     "MLB1144",
}


def fetch_mercadolivre(external_id: str) -> dict | None:
    """Busca preco via API publica do ML (sem token necessario).

    external_id formato: PLATAFORMA|TITULO  ex: PS5|Elden Ring
    """
    if "|" not in external_id:
        return None

    plataforma, titulo = external_id.split("|", 1)
    categoria = ML_CATEGORIAS.get(plataforma.upper())
    if not categoria:
        return None

    try:
        r = httpx.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={
                "q":        titulo,
                "category": categoria,
                "limit":    5,
                "sort":     "price_asc",
                "condition": "new",
            },
            headers={
                "Accept":     "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as exc:
        print(f"  [ml] erro ao buscar '{titulo}': {exc}")
        return None

    if not results:
        return None

    item  = results[0]
    preco = float(item.get("price", 0))
    if preco <= 0:
        return None

    return {
        "price":            round(preco, 2),
        "old_price":        None,
        "discount_percent": 0,
        "available":        True,
    }


# ── Amazon (scaffold) ─────────────────────────────────────────────────────────

def fetch_amazon(external_id: str) -> dict | None:
    """Scaffold: precisa de conta Amazon Associates + PA-API 5.0."""
    return None
