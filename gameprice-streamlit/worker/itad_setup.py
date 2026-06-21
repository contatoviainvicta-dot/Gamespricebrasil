"""Setup inicial do ITAD: indexa preços de GOG, Epic, Nuuvem, Fanatical.
Rode UMA VEZ via workflow itad-setup.
"""
import os, sys, time
import httpx
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))

URL       = os.environ["SUPABASE_URL"]
KEY       = os.environ["SUPABASE_SERVICE_KEY"]
ITAD_KEY  = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

# Mapeamento: ITAD shop_id (inteiro) → slug interno do banco
# Descobertos via teste diagnóstico
ITAD_SHOP_MAP = {
    35: "gog",          # GOG
    61: "steam",        # Steam (já temos, mas útil para confirmar)
    37: "humblestore",  # Humble Store
    # Epic e Nuuvem: IDs a confirmar no primeiro run
    # Adicionamos mais conforme os deals aparecerem
}

# Lojas que queremos criar no banco (além das já existentes)
LOJAS_CRIAR = {
    "gog":         "GOG",
    "humblestore": "Humble Store",
    "nuuvem":      "Nuuvem",
    "fanatical":   "Fanatical",
    "gmg":         "Green Man Gaming",
}


def itad_lookup(title: str) -> str | None:
    try:
        r = httpx.get(
            f"{ITAD_BASE}/games/search/v1",
            params={"title": title, "key": ITAD_KEY},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()
        return results[0]["id"] if results else None
    except Exception as e:
        print(f"  [lookup] '{title}': {e}")
        return None


def itad_prices_lote(itad_ids: list[str], country: str = "BR") -> dict:
    """Busca preços em lote. Retorna {itad_id: [deals]}."""
    try:
        r = httpx.post(
            f"{ITAD_BASE}/games/prices/v3",
            params={"key": ITAD_KEY, "country": country},
            json=itad_ids,
            headers={"Content-Type": "application/json",
                     "User-Agent": "GamePriceBrasil/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        return {item["id"]: item.get("deals", []) for item in r.json()}
    except Exception as e:
        print(f"  [prices] {e}")
        return {}


def run() -> None:
    if not ITAD_KEY:
        print("ERRO: ITAD_API_KEY não configurado")
        return

    sb = create_client(URL, KEY)

    # 1. Garantir lojas no banco e montar mapa slug→db_id
    lojas_db = {}
    for slug, nome in LOJAS_CRIAR.items():
        try:
            r = sb.table("stores").upsert(
                {"name": nome, "slug": slug, "active": True},
                on_conflict="slug"
            ).execute()
            lid = r.data[0]["id"] if r.data else None
            if not lid:
                g = sb.table("stores").select("id").eq("slug", slug).execute().data
                lid = g[0]["id"] if g else None
            if lid:
                lojas_db[slug] = lid
        except Exception as e:
            print(f"  Erro loja {slug}: {e}")

    # Incluir lojas já existentes (steam, epic)
    for row in sb.table("stores").select("id,slug").execute().data:
        lojas_db[row["slug"]] = row["id"]

    print(f"Lojas no banco: {list(lojas_db.keys())}")

    # 2. Descobrir IDs ITAD de todas as lojas (primeiro lote de teste)
    print("\n=== Mapeando IDs das lojas ITAD ===")
    test_id = itad_lookup("The Witcher 3")
    if test_id:
        deals_teste = itad_prices_lote([test_id]).get(test_id, [])
        shop_map_descoberto = {}
        for d in deals_teste:
            shop = d.get("shop", {})
            sid  = shop.get("id")
            nome = shop.get("name", "")
            shop_map_descoberto[sid] = nome
            print(f"  ITAD shop_id={sid} → {nome}")

        # Atualizar mapa com os descobertos
        for sid, nome in shop_map_descoberto.items():
            nome_lower = nome.lower()
            if "gog" in nome_lower:
                ITAD_SHOP_MAP[sid] = "gog"
            elif "epic" in nome_lower:
                ITAD_SHOP_MAP[sid] = "epic"
            elif "nuuvem" in nome_lower:
                ITAD_SHOP_MAP[sid] = "nuuvem"
            elif "fanatical" in nome_lower:
                ITAD_SHOP_MAP[sid] = "fanatical"
            elif "humble" in nome_lower:
                ITAD_SHOP_MAP[sid] = "humblestore"
            elif "green man" in nome_lower or "gmg" in nome_lower:
                ITAD_SHOP_MAP[sid] = "gmg"

    print(f"\nMapa de lojas ITAD: {ITAD_SHOP_MAP}")

    # Filtrar só as lojas que temos no banco E não são Steam
    lojas_alvo = {
        sid: slug for sid, slug in ITAD_SHOP_MAP.items()
        if slug != "steam" and slug in lojas_db
    }
    print(f"Lojas alvo: {lojas_alvo}")

    if not lojas_alvo:
        print("AVISO: nenhuma loja alvo mapeada. "
              "Verificar se GOG (id=35) está no ITAD_SHOP_MAP.")
        # Forçar GOG id=35 mesmo assim
        lojas_alvo[35] = "gog"

    # 3. Indexar todos os jogos
    print(f"\n=== Indexando catálogo ===")
    jogos = sb.table("games").select("id,title,slug")\
              .eq("platform", "PC").order("title").execute().data
    print(f"{len(jogos)} jogos para indexar")

    novos = erros = 0
    lote_ids   = []
    lote_jogos = []

    for i, jogo in enumerate(jogos, 1):
        itad_id = itad_lookup(jogo["title"])
        if not itad_id:
            erros += 1
            time.sleep(0.2)
            continue

        lote_ids.append(itad_id)
        lote_jogos.append({**jogo, "itad_id": itad_id})

        # Processa em lotes de 20
        if len(lote_ids) >= 20 or i == len(jogos):
            prices = itad_prices_lote(lote_ids)

            for jg in lote_jogos:
                deals = prices.get(jg["itad_id"], [])
                lojas_achadas = []

                for d in deals:
                    shop_id_num = d.get("shop", {}).get("id")  # inteiro
                    if shop_id_num not in lojas_alvo:
                        continue
                    slug      = lojas_alvo[shop_id_num]
                    db_loja_id = lojas_db.get(slug)
                    if not db_loja_id:
                        continue

                    external_id = f"ITAD|{slug}|{jg['itad_id']}"
                    url_deal    = d.get("url", "")
                    price_val   = d.get("price", {}).get("amount", 0)
                    currency    = d.get("price", {}).get("currency", "BRL")

                    try:
                        sb.table("game_store_offers").upsert({
                            "game_id":     jg["id"],
                            "store_id":    db_loja_id,
                            "external_id": external_id,
                            "product_url": url_deal,
                            "active":      True,
                        }, on_conflict="store_id,external_id").execute()
                        novos += 1
                        lojas_achadas.append(
                            f"{slug}({price_val}{currency})")
                    except Exception as e:
                        print(f"  Erro {jg['title']}/{slug}: {e}")

                if lojas_achadas:
                    print(f"  [{i}/{len(jogos)}] {jg['title'][:40]} "
                          f"→ {lojas_achadas}")

            lote_ids   = []
            lote_jogos = []
            time.sleep(0.5)

    print(f"\nResumo: {novos} ofertas criadas | {erros} sem ITAD ID")


if __name__ == "__main__":
    run()
