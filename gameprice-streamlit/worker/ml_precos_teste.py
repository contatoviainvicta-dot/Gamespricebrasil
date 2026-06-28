"""TESTE 2: API pública do ML com MLB id extraído da URL normal.

Agora extrai o item_id (MLB...) da URL normal do produto (não do meli.la),
que é onde o ID realmente está. Testa se a API pública devolve o preço.
"""
import os, re
import httpx
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Teste fixo com o Zelda (enquanto não há ml_url cadastrada)
TESTE_FIXO = "MLB6576972562"


def extrair_item_id(url: str) -> str:
    """Extrai o item_id real (MLB seguido de dígitos) da URL normal."""
    if not url:
        return None
    # item_id no filtro, wid, ou MLB solto — pega o que tem dígitos (não o MLBU de catálogo)
    for pat in [r'item_id[%:]+MLB(\d{6,})', r'wid=MLB(\d{6,})', r'MLB(\d{9,})']:
        m = re.search(pat, url)
        if m:
            return "MLB" + m.group(1)
    return None


def buscar_preco(mlb: str) -> dict:
    try:
        r = httpx.get(f"https://api.mercadolibre.com/items/{mlb}",
                      timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        print(f"    API /items status: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            return {"preco": d.get("price"), "titulo": d.get("title"),
                    "status": d.get("status")}
        else:
            print(f"    corpo: {r.text[:150]}")
    except Exception as e:
        print(f"    erro: {e}")
    return {}


def run():
    print("=== TESTE 2: API pública ML ===\n")

    # 1. Testar com o MLB fixo do Zelda
    print(f"[1] Teste direto com MLB fixo: {TESTE_FIXO}")
    res = buscar_preco(TESTE_FIXO)
    if res.get("preco"):
        print(f"    ✓ PREÇO: R$ {res['preco']} — {res.get('titulo','')[:40]}\n")
    else:
        print(f"    ✗ sem preço\n")

    # 2. Testar com produtos que tenham ml_url cadastrada
    sb = create_client(URL, KEY)
    produtos = sb.table("ml_afiliados").select("*").eq("ativo", True).execute().data
    com_url = [p for p in produtos if p.get("ml_url")]
    print(f"[2] {len(com_url)} produtos com ml_url cadastrada")
    for p in com_url[:5]:
        mlb = extrair_item_id(p.get("ml_url"))
        print(f"  {p['titulo_ml'][:40]} → {mlb}")
        if mlb:
            res = buscar_preco(mlb)
            if res.get("preco"):
                print(f"    ✓ R$ {res['preco']}")

    print("\n=== Fim ===")


if __name__ == "__main__":
    run()
