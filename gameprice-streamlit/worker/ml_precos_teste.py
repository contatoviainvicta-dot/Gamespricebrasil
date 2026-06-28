"""TESTE: coletar preços do ML via API pública.

Roda no GitHub Actions para testar se a API pública do ML responde
do ambiente real (o sandbox dá 403, mas o Actions pode funcionar).

Fluxo:
1. Pega produtos ML cadastrados
2. Segue o redirect do meli.la → descobre URL real → extrai MLB id
3. Busca preço na API pública api.mercadolibre.com/items/MLB...
4. Mostra o resultado (sem gravar ainda — é teste)
"""
import os, re
import httpx
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def extrair_mlb(url_afiliado: str) -> str:
    """Segue o redirect do meli.la e extrai o ID MLB da URL final."""
    try:
        # Seguir redirecionamentos
        r = httpx.get(url_afiliado, follow_redirects=True, timeout=15,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        url_final = str(r.url)
        print(f"    URL final: {url_final[:80]}")
        # Procurar padrão MLB seguido de números
        m = re.search(r'MLB-?(\d{6,})', url_final)
        if m:
            return "MLB" + m.group(1)
        # Tentar no corpo da página
        m2 = re.search(r'MLB-?(\d{9,})', r.text[:5000])
        if m2:
            return "MLB" + m2.group(1)
    except Exception as e:
        print(f"    erro ao extrair MLB: {e}")
    return None


def buscar_preco(mlb: str) -> dict:
    """Busca preço via API pública do ML."""
    try:
        r = httpx.get(f"https://api.mercadolibre.com/items/{mlb}",
                      timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        print(f"    API status: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            return {"preco": d.get("price"), "titulo": d.get("title")}
    except Exception as e:
        print(f"    erro API: {e}")
    return {}


def run():
    sb = create_client(URL, KEY)
    produtos = sb.table("ml_afiliados").select("*").eq("ativo", True).limit(5).execute().data
    print(f"=== TESTE de coleta de preço ML — {len(produtos)} produtos ===\n")

    for p in produtos:
        print(f"Produto: {p['titulo_ml'][:45]}")
        print(f"  Link: {p['afiliado_url']}")
        mlb = p.get("ml_id") or extrair_mlb(p["afiliado_url"])
        if not mlb:
            print("  ✗ Não consegui extrair o MLB id\n")
            continue
        print(f"  MLB id: {mlb}")
        res = buscar_preco(mlb)
        if res.get("preco"):
            print(f"  ✓ PREÇO ATUAL: R$ {res['preco']}")
        else:
            print(f"  ✗ Não consegui o preço")
        print()

    print("=== Fim do teste ===")


if __name__ == "__main__":
    run()
