"""Worker de preços Steam — paginado e otimizado.
Roda a cada 6h via GitHub Actions.
"""
import os, sys, time
import httpx
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Limite de jogos por execução para caber em <6h do GitHub Actions
# 2500 jogos × ~1.3s = ~55min. O resto é atualizado no próximo ciclo.
MAX_POR_CICLO = int(os.environ.get("MAX_GAMES", "1500"))


def fetch_all_offers(sb, store_slug: str) -> list:
    """Busca TODAS as ofertas ativas paginando (Supabase limita a 1000)."""
    store = sb.table("stores").select("id").eq("slug", store_slug).execute().data
    if not store:
        return []
    store_id = store[0]["id"]

    todas = []
    page = 0
    size = 1000
    while True:
        batch = (sb.table("game_store_offers")
                 .select("id, external_id, last_checked")
                 .eq("store_id", store_id)
                 .eq("active", True)
                 .range(page * size, page * size + size - 1)
                 .execute().data)
        if not batch:
            break
        todas.extend(batch)
        if len(batch) < size:
            break
        page += 1
    return todas


def fetch_steam_batch(appids: list[str], _retry: int = 0) -> dict:
    """Busca preço de um appid. Em caso de 429, espera e tenta de novo."""
    if not appids:
        return {}
    try:
        r = httpx.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": ",".join(appids), "cc": "br", "l": "portuguese",
                    "filters": "price_overview"},
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 429:
            if _retry < 3:
                espera = 30 * (_retry + 1)   # 30s, 60s, 90s
                print(f"  [429] Steam limitou — aguardando {espera}s "
                      f"(tentativa {_retry+1}/3)...")
                time.sleep(espera)
                return fetch_steam_batch(appids, _retry + 1)
            else:
                print(f"  [429] desistindo de {appids} após 3 tentativas")
                return {}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [steam_batch] erro: {e}")
        return {}


def run() -> None:
    sb = create_client(URL, KEY)

    offers = fetch_all_offers(sb, "steam")
    print(f"=== Steam: {len(offers)} ofertas ativas no total ===")

    # Priorizar jogos não checados recentemente (last_checked mais antigo primeiro)
    offers.sort(key=lambda o: o.get("last_checked") or "")
    offers = offers[:MAX_POR_CICLO]
    print(f"Processando {len(offers)} neste ciclo (máx {MAX_POR_CICLO})")

    rows = []
    checked_ids = []
    # A API appdetails aceita múltiplos IDs mas só retorna price_overview de 1 por vez
    # de forma confiável. Vamos em lotes pequenos com pausa.
    for i, o in enumerate(offers, 1):
        appid = o["external_id"]
        data = fetch_steam_batch([appid])
        raw = data.get(str(appid), {})
        if raw.get("success"):
            d = raw.get("data", {})
            po = d.get("price_overview") if isinstance(d, dict) else None
            if po:
                rows.append({
                    "offer_id": o["id"],
                    "price": round(po["final"]/100, 2),
                    "old_price": round(po["initial"]/100, 2) if po.get("initial") else None,
                    "discount_percent": po.get("discount_percent", 0),
                    "available": True,
                })
            else:
                # Jogo gratuito ou sem preço
                rows.append({
                    "offer_id": o["id"], "price": 0.0,
                    "old_price": None, "discount_percent": 0, "available": True,
                })
            checked_ids.append(o["id"])
        if i % 100 == 0:
            print(f"  [{i}/{len(offers)}] {len(rows)} preços coletados")
        time.sleep(2.0)

    # Gravar preços em lotes
    if rows:
        for start in range(0, len(rows), 50):
            sb.table("prices").insert(rows[start:start+50]).execute()

    # Atualizar last_checked
    if checked_ids:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for start in range(0, len(checked_ids), 50):
            batch = checked_ids[start:start+50]
            sb.table("game_store_offers").update({"last_checked": now})\
              .in_("id", batch).execute()

    print(f"\nSteam: {len(rows)} preços gravados")


if __name__ == "__main__":
    run()
