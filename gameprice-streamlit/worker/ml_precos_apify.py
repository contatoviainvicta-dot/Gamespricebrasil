"""Coleta preços do ML via Apify (scraper pago, usa crédito).

Para cada produto com ml_url cadastrada, chama o Apify para
buscar o preço atual e grava em preco_auto.

Secrets necessários:
  APIFY_TOKEN  → token da API do Apify
"""
import os, re
import httpx
from datetime import datetime, timezone
from supabase import create_client

URL   = os.environ["SUPABASE_URL"]
KEY   = os.environ["SUPABASE_SERVICE_KEY"]
APIFY = os.environ["APIFY_TOKEN"]

# Actor do Apify para scraping de produto ML (aceita URLs de produto)
ACTOR = "trudax~mercadolibre-scraper"


def limpar_url(url: str) -> str:
    """Remove parâmetros de tracking, mantém só a URL base do produto."""
    if not url:
        return url
    # Cortar em # e em ? para limpar tracking
    url = url.split("#")[0].split("?")[0]
    return url


def buscar_preco_apify(url_produto: str) -> float:
    """Chama o Apify para extrair o preço de uma URL de produto ML."""
    try:
        endpoint = (f"https://api.apify.com/v2/acts/{ACTOR}/"
                    f"run-sync-get-dataset-items?token={APIFY}")
        payload = {
            "startUrls": [{"url": url_produto}],
            "maxItems": 1,
        }
        r = httpx.post(endpoint, json=payload, timeout=120)
        print(f"    Apify status: {r.status_code}")
        if r.status_code in (200, 201):
            data = r.json()
            if data and isinstance(data, list):
                item = data[0]
                # O preço pode vir em campos diferentes conforme o actor
                for campo in ["price", "preco", "currentPrice", "salePrice"]:
                    if item.get(campo):
                        return float(str(item[campo]).replace(",", "."))
                print(f"    resposta sem campo de preço: {list(item.keys())[:8]}")
        else:
            print(f"    corpo: {r.text[:150]}")
    except Exception as e:
        print(f"    erro Apify: {e}")
    return None


def run():
    sb = create_client(URL, KEY)
    produtos = (sb.table("ml_afiliados").select("*")
                .eq("ativo", True).execute().data)
    com_url = [p for p in produtos if p.get("ml_url")]
    print(f"=== Coleta de preços ML via Apify ===")
    print(f"{len(com_url)} produtos com URL de preço\n")

    atualizados = 0
    for p in com_url:
        print(f"Produto: {p['titulo_ml'][:45]}")
        url_limpa = limpar_url(p["ml_url"])
        preco = buscar_preco_apify(url_limpa)
        if preco and preco > 0:
            sb.table("ml_afiliados").update({
                "preco_auto": preco,
                "preco_auto_em": datetime.now(timezone.utc).isoformat(),
            }).eq("id", p["id"]).execute()
            print(f"  ✓ Preço: R$ {preco:.2f}\n")
            atualizados += 1
        else:
            print(f"  ✗ Não obteve preço\n")

    print(f"=== {atualizados}/{len(com_url)} preços atualizados ===")


if __name__ == "__main__":
    run()
