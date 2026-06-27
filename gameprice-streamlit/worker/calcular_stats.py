"""Popula price_statistics: mínimos histórico/30d/90d por oferta.

Roda 1x por dia. Lê o histórico de prices e calcula as estatísticas
que alimentam a aba 🏆 Históricos e os cards de mínimo 30/90 dias.
"""
import os
from datetime import datetime, timedelta, timezone
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def fetch_all_offers(sb) -> list:
    """Todas as ofertas ativas, paginando (limite 1000 do Supabase)."""
    todas, page, size = [], 0, 1000
    while True:
        batch = (sb.table("game_store_offers")
                 .select("id, old_price")
                 .eq("active", True)
                 .range(page*size, page*size+size-1)
                 .execute().data)
        if not batch:
            break
        todas.extend(batch)
        if len(batch) < size:
            break
        page += 1
    return todas


def fetch_prices(sb, offer_id: str, desde_iso: str = None) -> list:
    """Preços > 0 de uma oferta, opcionalmente a partir de uma data."""
    q = (sb.table("prices").select("price")
         .eq("offer_id", offer_id).gt("price", 0))
    if desde_iso:
        q = q.gte("captured_at", desde_iso)
    return [float(r["price"]) for r in q.execute().data]


def run():
    sb = create_client(URL, KEY)
    now = datetime.now(timezone.utc)
    d30 = (now - timedelta(days=30)).isoformat()
    d90 = (now - timedelta(days=90)).isoformat()

    offers = fetch_all_offers(sb)
    print(f"=== Calculando stats de {len(offers)} ofertas ===")

    upserts = []
    processados = 0
    for o in offers:
        oid = o["id"]
        todos = fetch_prices(sb, oid)
        if not todos:
            continue
        p30 = fetch_prices(sb, oid, d30)
        p90 = fetch_prices(sb, oid, d90)
        atual = todos[-1]  # último capturado (já vem ordenado por captured_at no insert)
        orig  = float(o.get("old_price") or 0)
        disc  = int((1 - min(todos)/orig)*100) if orig > min(todos) else 0

        upserts.append({
            "offer_id":       oid,
            "price_current":  atual,
            "price_min_ever": min(todos),
            "price_min_30d":  min(p30) if p30 else None,
            "price_min_90d":  min(p90) if p90 else None,
            "price_avg_90d":  round(sum(p90)/len(p90), 2) if p90 else None,
            "discount_max":   disc,
            "updated_at":     now.isoformat(),
        })
        processados += 1

        # Gravar em lotes de 100
        if len(upserts) >= 100:
            sb.table("price_statistics").upsert(upserts, on_conflict="offer_id").execute()
            print(f"  {processados} processados...")
            upserts = []

    if upserts:
        sb.table("price_statistics").upsert(upserts, on_conflict="offer_id").execute()

    total = len(sb.table("price_statistics").select("offer_id").execute().data)
    print(f"=== {processados} ofertas com stats | tabela tem ~{total} registros ===")


if __name__ == "__main__":
    run()
