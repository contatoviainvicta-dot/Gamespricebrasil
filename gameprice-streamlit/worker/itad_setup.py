"""Setup inicial do ITAD: descobre os ITAD IDs dos jogos e indexa preços
de GOG, Epic, Nuuvem, Fanatical e outras lojas.

Rode UMA VEZ (workflow itad-setup) depois de configurar ITAD_API_KEY.
"""
import os, sys, time, json
import httpx
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))

URL      = os.environ["SUPABASE_URL"]
KEY      = os.environ["SUPABASE_SERVICE_KEY"]
ITAD_KEY = os.environ.get("ITAD_API_KEY", "")
ITAD_BASE = "https://api.isthereanydeal.com"

# Lojas que queremos cobrir — IDs reais do ITAD
# Descobertos via GET /shops/v1
LOJAS_ALVO = {
    "gog":          "GOG",
    "epic":         "Epic Games",
    "nuuvem":       "Nuuvem",
    "fanatical":    "Fanatical",
    "humblestore":  "Humble Store",
    "gmg":          "Green Man Gaming",
}


def get_itad_shops() -> dict:
    """Busca mapeamento id→name das lojas do ITAD."""
    try:
        r = httpx.get(
            f"{ITAD_BASE}/shops/v1",
            params={"key": ITAD_KEY},
            headers={"User-Agent": "GamePriceBrasil/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        shops = r.json()
        mapa = {s["id"]: s["title"] for s in shops}
        print(f"Lojas disponíveis no ITAD: {len(mapa)}")
        # Mostrar lojas relevantes
        for sid, nome in mapa.items():
            if any(k in sid.lower() or k in nome.lower()
                   for k in ["gog","epic","nuuvem","fanatical","humble"]):
                print(f"  {sid} → {nome}")
        return mapa
    except Exception as e:
        print(f"  [shops] erro: {e}")
        return {}


def itad_lookup(title: str) -> str | None:
    """Busca ITAD ID por título."""
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


def itad_prices(itad_ids: list[str]) -> dict:
    """Busca preços de múltiplos jogos — tenta com BR e sem country."""
    resultado = {}
    for country in ["BR", None]:
        try:
            params = {"key": ITAD_KEY}
            if country:
                params["country"] = country
            r = httpx.post(
                f"{ITAD_BASE}/games/prices/v3",
                params=params,
                json=itad_ids,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent":   "GamePriceBrasil/1.0",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            for item in data:
                gid   = item.get("id", "")
                deals = item.get("deals", [])
                if deals and gid not in resultado:
                    resultado[gid] = deals
            if resultado:
                print(f"  Preços obtidos com country={country}: {len(resultado)} jogos")
                break
        except Exception as e:
            print(f"  [prices] country={country}: {e}")

    return resultado


def run() -> None:
    if not ITAD_KEY:
        print("ERRO: ITAD_API_KEY não configurado")
        return

    sb = create_client(URL, KEY)

    # 1. Descobrir IDs reais das lojas no ITAD
    print("=== Descobrindo lojas do ITAD ===")
    shops_disponiveis = get_itad_shops()

    # 2. Garantir que as lojas existem no banco
    lojas_db = {}
    for slug, nome in LOJAS_ALVO.items():
        try:
            r = sb.table("stores").upsert(
                {"name": nome, "slug": slug, "active": True},
                on_conflict="slug"
            ).execute()
            if r.data:
                lojas_db[slug] = r.data[0]["id"]
            else:
                g = sb.table("stores").select("id").eq("slug", slug).execute().data
                if g:
                    lojas_db[slug] = g[0]["id"]
        except Exception as e:
            print(f"  Erro ao criar loja {slug}: {e}")

    print(f"\nLojas no banco: {list(lojas_db.keys())}")

    # 3. Testar com um jogo conhecido antes de processar tudo
    print("\n=== Teste com The Witcher 3 ===")
    test_id = itad_lookup("The Witcher 3")
    print(f"ITAD ID: {test_id}")
    if test_id:
        test_prices = itad_prices([test_id])
        deals = test_prices.get(test_id, [])
        print(f"Deals encontrados: {len(deals)}")
        for d in deals[:10]:
            shop = d.get("shop", {})
            price = d.get("price", {})
            print(f"  shop_id={shop.get('id')} | "
                  f"shop_name={shop.get('name')} | "
                  f"price={price.get('amount')} {price.get('currency')}")

    # 4. Processar todos os jogos
    print("\n=== Indexando catálogo completo ===")
    jogos = sb.table("games").select("id,title,slug")\
              .eq("platform","PC").order("title").execute().data
    print(f"{len(jogos)} jogos para indexar")

    novos = 0
    erros = 0
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
            prices = itad_prices(lote_ids)

            for jg in lote_jogos:
                deals = prices.get(jg["itad_id"], [])
                lojas_achadas = []
                for d in deals:
                    shop_id = d.get("shop", {}).get("id", "")
                    # Verifica se é uma loja que queremos
                    for slug in LOJAS_ALVO:
                        if slug in shop_id.lower():
                            loja_db_id = lojas_db.get(slug)
                            if not loja_db_id:
                                continue
                            external_id = f"ITAD|{slug}|{jg['itad_id']}"
                            url_deal = d.get("url", "")
                            try:
                                sb.table("game_store_offers").upsert({
                                    "game_id":     jg["id"],
                                    "store_id":    loja_db_id,
                                    "external_id": external_id,
                                    "product_url": url_deal or f"https://isthereanydeal.com/",
                                    "active":      True,
                                }, on_conflict="store_id,external_id").execute()
                                novos += 1
                                lojas_achadas.append(slug)
                            except Exception as e:
                                print(f"  Erro ao inserir {jg['title']}/{slug}: {e}")

                status = f"lojas: {lojas_achadas}" if lojas_achadas else "sem lojas alvo"
                print(f"  [{i}/{len(jogos)}] {jg['title'][:40]} → {status}")

            lote_ids   = []
            lote_jogos = []
            time.sleep(0.5)  # Pausa entre lotes

    print(f"\nResumo: {novos} ofertas criadas | {erros} sem ITAD ID")


if __name__ == "__main__":
    run()
