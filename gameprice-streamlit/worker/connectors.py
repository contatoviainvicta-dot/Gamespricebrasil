"""Conectores de loja para o worker.

Steam: API publica de storefront (sem credencial).
Mercado Livre / Amazon: deixados como scaffold (precisam de token/credencial).
"""
import httpx


def fetch_steam(appid: str, cc: str = "br", lang: str = "portuguese") -> dict | None:
    """Retorna preço atual de um jogo na Steam pelo appid."""
    url = "https://store.steampowered.com/api/appdetails"
    try:
        r = httpx.get(
            url,
            params={"appids": appid, "cc": cc, "l": lang, "filters": "price_overview"},
            timeout=20,
        )
        r.raise_for_status()
        raw = r.json().get(str(appid), {})
    except Exception as exc:
        print(f"  [steam] erro no appid {appid}: {exc}")
        return None

    if not raw.get("success"):
        return None

    # Steam às vezes retorna data como lista — pega o primeiro elemento
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


def fetch_mercadolivre(external_id: str) -> dict | None:
    """Scaffold: a API do Mercado Livre exige token OAuth. Implementar depois."""
    return None
