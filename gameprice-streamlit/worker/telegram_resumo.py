"""Post diário de resumo: Top ofertas do dia numa única mensagem.

Roda 1x por dia. Lista as melhores ofertas num post compacto,
sem floodar o canal. Complementa o telegram_deals.py (que posta
deals individuais em tempo real).
"""
import os
import httpx
from datetime import datetime
from supabase import create_client

URL   = os.environ["SUPABASE_URL"]
KEY   = os.environ["SUPABASE_SERVICE_KEY"]
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT  = os.environ["TELEGRAM_CHAT_ID"]
APP   = os.environ.get("APP_URL", "https://gameprice.streamlit.app")


def enviar(texto: str) -> bool:
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                  "disable_web_page_preview": "true"},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  [telegram] erro {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"  [telegram] exceção: {e}")
        return False


def run():
    sb = create_client(URL, KEY)
    print("=== Resumo diário Top Ofertas ===")

    deals = (sb.table("v_game_offers")
             .select("title,store,price,old_price,discount_percent")
             .gte("discount_percent", 50)
             .order("discount_percent", desc=True)
             .limit(15)
             .execute().data)

    if not deals:
        print("Sem ofertas para o resumo.")
        return

    hoje = datetime.now().strftime("%d/%m")
    linhas = [f"🔥 <b>TOP OFERTAS DO DIA — {hoje}</b>\n"]
    for d in deals[:12]:
        pr = float(d.get("price") or 0)
        if pr <= 0:
            continue
        pc = d.get("discount_percent", 0)
        linhas.append(f"🎮 <b>{d['title']}</b>\n"
                      f"   <b>R$ {pr:.2f}</b> (-{pc}%) · {d['store']}")
    linhas.append(f"\n🔗 Ver tudo: <a href='{APP}'>GamePrice Brasil</a>")
    linhas.append("#ofertas #games #promoção")

    texto = "\n".join(linhas)
    if enviar(texto):
        print(f"  ✓ Resumo postado com {len(deals[:12])} ofertas")
    else:
        print("  ✗ Falha ao postar resumo")


if __name__ == "__main__":
    run()
