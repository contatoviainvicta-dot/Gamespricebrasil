"""Conectores de loja para o worker.

Steam  : API pública de storefront. Operante.
Epic   : API não-documentada (freeGamesPromotions + GraphQL). Operante.
ML     : API pública. Bloqueada por política - aguardando afiliados.
Amazon : Scaffold.
"""
import time
import httpx


# ── Steam ─────────────────────────────────────────────────────────────────────

def fetch_steam(appid: str, cc: str = "br", lang: str = "portuguese") -> dict | None:
    """Retorna preço atual de um jogo na Steam pelo appid."""
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


# ── Epic Games ────────────────────────────────────────────────────────────────

EPIC_FREE_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=pt-BR&country=BR&allowCountries=BR"
)

EPIC_GRAPHQL_URL = "https://graphql.epicgames.com/graphql"

EPIC_SEARCH_QUERY = """
query searchStoreQuery(
  $keywords: String
  $country: String!
  $locale: String
  $count: Int
) {
  Catalog {
    searchStore(
      keywords: $keywords
      country: $country
      locale: $locale
      count: $count
      sortBy: "relevancy"
      category: "games/edition/base"
    ) {
      elements {
        title
        productSlug
        urlSlug
        price(country: $country) {
          totalPrice {
            discountPrice
            originalPrice
            discount
            fmtPrice(locale: "pt-BR") {
              originalPrice
              discountPrice
            }
          }
        }
        keyImages {
          type
          url
        }
      }
    }
  }
}
"""


def fetch_epic_free_games() -> dict:
    """Retorna jogos gratuitos AGORA e PRÓXIMA SEMANA na Epic.

    Retorno:
        {
            "current": [{"title": ..., "slug": ..., "image_url": ...,
                         "end_date": ..., "store_url": ...}],
            "next":    [{"title": ..., "slug": ..., "image_url": ...,
                         "start_date": ...}],
        }
    """
    result = {"current": [], "next": []}
    try:
        r = httpx.get(
            EPIC_FREE_URL,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "application/json",
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
        slug   = el.get("productSlug") or el.get("urlSlug") or ""
        promos = el.get("promotions") or {}
        imgs   = el.get("keyImages", [])

        # Pega a melhor imagem disponível
        image_url = ""
        for tipo in ["Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultOpened"]:
            img = next((i["url"] for i in imgs if i.get("type") == tipo), None)
            if img:
                image_url = img
                break

        store_url = f"https://store.epicgames.com/pt-BR/p/{slug}"

        # Gratuito AGORA
        offers_now = promos.get("promotionalOffers", [])
        for offer_group in offers_now:
            for offer in offer_group.get("promotionalOffers", []):
                disc = offer.get("discountSetting", {})
                if disc.get("discountPercentage", -1) == 0:
                    result["current"].append({
                        "title":     title,
                        "slug":      slug,
                        "image_url": image_url,
                        "end_date":  offer.get("endDate", ""),
                        "store_url": store_url,
                    })

        # Gratuito NA PRÓXIMA SEMANA
        offers_next = promos.get("upcomingPromotionalOffers", [])
        for offer_group in offers_next:
            for offer in offer_group.get("promotionalOffers", []):
                disc = offer.get("discountSetting", {})
                if disc.get("discountPercentage", -1) == 0:
                    result["next"].append({
                        "title":      title,
                        "slug":       slug,
                        "image_url":  image_url,
                        "start_date": offer.get("startDate", ""),
                        "store_url":  store_url,
                    })

    return result


def fetch_epic_price(slug: str) -> dict | None:
    """Busca preço de um jogo na Epic pelo slug do produto.

    external_id formato: EPIC|slug-do-jogo
    ex: EPIC|cyberpunk-2077
    """
    if not slug:
        return None

    try:
        r = httpx.post(
            EPIC_GRAPHQL_URL,
            json={
                "query":     EPIC_SEARCH_QUERY,
                "variables": {
                    "keywords": slug.replace("-", " "),
                    "country":  "BR",
                    "locale":   "pt-BR",
                    "count":    3,
                },
            },
            headers={
                "User-Agent":   "Mozilla/5.0",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        r.raise_for_status()
        elements = (
            r.json()
            .get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
    except Exception as exc:
        print(f"  [epic_price] erro para slug '{slug}': {exc}")
        return None

    if not elements:
        return None

    # Pega o primeiro resultado (mais relevante)
    el    = elements[0]
    tp    = el.get("price", {}).get("totalPrice", {})
    disc  = tp.get("discountPrice", 0)
    orig  = tp.get("originalPrice", 0)

    if orig == 0 and disc == 0:
        return None  # Jogo sem preço listado

    discount_pct = int(((orig - disc) / orig) * 100) if orig > 0 else 0

    return {
        "price":            round(disc / 100, 2),
        "old_price":        round(orig / 100, 2) if orig != disc else None,
        "discount_percent": discount_pct,
        "available":        True,
    }


def fetch_epic(external_id: str) -> dict | None:
    """Dispatcher para ofertas da Epic.

    external_id formato: EPIC|slug
    """
    if not external_id.startswith("EPIC|"):
        return None
    slug = external_id.split("|", 1)[1]
    return fetch_epic_price(slug)


# ── Mercado Livre (bloqueado por política - aguardando aprovação de afiliados) ─

ML_CATEGORIAS = {
    "PS5":    "MLB1132",
    "PS4":    "MLB1133",
    "XBOX":   "MLB1069",
    "SWITCH": "MLB1131",
    "PC":     "MLB1144",
}


def fetch_mercadolivre(external_id: str) -> dict | None:
    """API pública do ML — retorna 403 de IPs de datacenter.
    Aguardando aprovação no programa de afiliados para usar feed oficial.
    """
    return None


# ── Amazon (scaffold) ─────────────────────────────────────────────────────────

def fetch_amazon(external_id: str) -> dict | None:
    """Scaffold: precisa de conta Amazon Associates + PA-API 5.0."""
    return None
