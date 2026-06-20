"""Conectores de loja para o worker.

Steam  : API publica de storefront (sem credencial). Operante.
ML     : API oficial do Mercado Livre com client_credentials. Operante.
Amazon : Scaffold — precisa de conta Amazon Associates + PA-API.
"""
import os
import httpx

# ── Steam ────────────────────────────────────────────────────────────────────

def fetch_steam(appid: str, cc: str = "br", lang: str = "portuguese") -> dict | None:
    """Retorna preco atual de um jogo na Steam pelo appid."""
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

# Categorias de jogos no ML Brasil
ML_CATEGORIAS = {
    "PS5":    "MLB1132",
    "PS4":    "MLB1133",
    "XBOX":   "MLB1069",
    "SWITCH": "MLB1131",
    "PC":     "MLB1144",
}

_ml_token: dict = {}   # cache em memoria do token


def _ml_get_token(client_id: str, client_secret: str) -> str | None:
    """Obtem token OAuth2 client_credentials do Mercado Livre."""
    import time
    global _ml_token
    if _ml_token.get("expires_at", 0) > time.time() + 60:
        return _ml_token["access_token"]
    try:
        r = httpx.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        import time as t
        _ml_token = {
            "access_token": data["access_token"],
            "expires_at":   t.time() + data.get("expires_in", 21600),
        }
        return _ml_token["access_token"]
    except Exception as exc:
        print(f"  [ml] erro ao obter token: {exc}")
        return None


def fetch_mercadolivre(external_id: str) -> dict | None:
    """Busca preco de um produto no ML pelo ID externo.

    O external_id tem o formato: PLATAFORMA|TITULO_DO_JOGO
    Exemplo: PS5|Elden Ring
    Isso permite buscar o jogo certo na categoria certa.
    """
    client_id     = os.environ.get("ML_CLIENT_ID", "")
    client_secret = os.environ.get("ML_CLIENT_SECRET", "")

    if not client_id:
        return None   # credenciais nao configuradas

    # Decodifica o external_id
    if "|" not in external_id:
        return None
    plataforma, titulo = external_id.split("|", 1)
    categoria = ML_CATEGORIAS.get(plataforma.upper())
    if not categoria:
        return None

    # Busca publica (nao precisa de token para pesquisa)
    try:
        params = {
            "q":        titulo,
            "category": categoria,
            "limit":    5,
            "sort":     "price_asc",
            "condition": "new",
        }
        headers = {"Accept": "application/json"}
        token = _ml_get_token(client_id, client_secret)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        r = httpx.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params=params,
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as exc:
        print(f"  [ml] erro ao buscar '{titulo}': {exc}")
        return None

    if not results:
        return None

    # Pega o item mais barato (ja ordenado por preco_asc)
    item = results[0]
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
