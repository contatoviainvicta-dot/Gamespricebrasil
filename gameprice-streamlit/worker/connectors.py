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
        catalogNs {
          mappings(pageType: "productHome") {
            pageSlug
            pageType
          }
        }
        price(country: $country) {
          totalPrice {
            discountPrice
            originalPrice
            discount
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


def _epic_store_url(el: dict) -> str:
    """Monta a URL correta da Epic a partir do elemento da API.

    A Epic tem três campos de slug diferentes — tenta na ordem
    de confiabilidade até encontrar um válido.
    """
    # 1. catalogNs.mappings → pageSlug (mais confiável)
    mappings = (
        el.get("catalogNs", {})
          .get("mappings", []) or []
    )
    for m in mappings:
        if m.get("pageType") == "productHome" and m.get("pageSlug"):
            return f"https://store.epicgames.com/pt-BR/p/{m['pageSlug']}"

    # 2. productSlug
    slug = el.get("productSlug", "")
    if slug and slug != "[]":
        # Remove sufixo /home se existir
        slug = slug.replace("/home", "").strip("/")
        if slug:
            return f"https://store.epicgames.com/pt-BR/p/{slug}"

    # 3. urlSlug
    slug = el.get("urlSlug", "")
    if slug:
        return f"https://store.epicgames.com/pt-BR/p/{slug}"

    # 4. Fallback: página de jogos gratuitos
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

        # Melhor imagem disponível
        image_url = ""
        for tipo in ["Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultOpened"]:
            img = next((i["url"] for i in imgs if i.get("type") == tipo), None)
            if img:
                image_url = img
                break

        store_url = _epic_store_url(el)

        # Gratuito AGORA
        for offer_group in promos.get("promotionalOffers", []):
            for offer in offer_group.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["current"].append({
                        "title":     title,
                        "image_url": image_url,
                        "end_date":  offer.get("endDate", ""),
                        "store_url": store_url,
                    })

        # Gratuito NA PRÓXIMA SEMANA
        for offer_group in promos.get("upcomingPromotionalOffers", []):
            for offer in offer_group.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", -1) == 0:
                    result["next"].append({
                        "title":      title,
                        "image_url":  image_url,
                        "start_date": offer.get("startDate", ""),
                        "store_url":  store_url,
                    })

    return result


def fetch_epic(external_id: str) -> dict | None:
    """Busca preço de um jogo na Epic pelo slug. external_id = EPIC|slug"""
    if not external_id.startswith("EPIC|"):
        return None
    slug = external_id.split("|", 1)[1]

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

    el   = elements[0]
    tp   = el.get("price", {}).get("totalPrice", {})
    disc = tp.get("discountPrice", 0)
    orig = tp.get("originalPrice", 0)

    if orig == 0 and disc == 0:
        return None

    discount_pct = int(((orig - disc) / orig) * 100) if orig > 0 else 0

    return {
        "price":            round(disc / 100, 2),
        "old_price":        round(orig / 100, 2) if orig != disc else None,
        "discount_percent": discount_pct,
        "available":        True,
    }


# ── Mercado Livre (bloqueado por política — aguardando afiliados) ─────────────

def fetch_mercadolivre(external_id: str) -> dict | None:
    return None


# ── Amazon (scaffold) ─────────────────────────────────────────────────────────

def fetch_amazon(external_id: str) -> dict | None:
    return None
