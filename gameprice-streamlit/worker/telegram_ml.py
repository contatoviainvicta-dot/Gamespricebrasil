"""Posta produtos do Mercado Livre (com links de afiliado) no canal.

Estes são os posts que GERAM RECEITA — cada clique que vira venda
paga comissão (até 16%). Roda em rodízio para não repetir sempre
os mesmos produtos.

Posta produtos ML ativos, priorizando os de maior comissão,
em rodízio (os menos postados recentemente primeiro).
"""
import os, time
import httpx
from datetime import datetime, timezone
from supabase import create_client

URL   = os.environ["SUPABASE_URL"]
KEY   = os.environ["SUPABASE_SERVICE_KEY"]
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT  = os.environ["TELEGRAM_CHAT_ID"]
APP   = os.environ.get("APP_URL", "https://gameprice.streamlit.app")

MAX_POR_CICLO = 4   # posta até 4 produtos ML por execução


def enviar(texto: str, imagem: str = None) -> bool:
    try:
        if imagem:
            r = httpx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                data={"chat_id": CHAT, "caption": texto, "parse_mode": "HTML"},
                params={"photo": imagem},
                timeout=20,
            )
        else:
            r = httpx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                data={"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                      "disable_web_page_preview": "false"},
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
    print("=== Produtos ML no Telegram (afiliados) ===")

    produtos = (sb.table("ml_afiliados")
                .select("*")
                .eq("ativo", True)
                .order("ultimo_post_tg", desc=False, nullsfirst=True)
                .order("comissao_pct", desc=True)
                .limit(MAX_POR_CICLO)
                .execute().data)

    if not produtos:
        print("Nenhum produto ML ativo para postar.")
        return

    print(f"{len(produtos)} produtos para postar")
    postados = 0

    for p in produtos:
        titulo = p["titulo_ml"]
        preco  = p.get("preco")
        plat   = p.get("plataforma") or ""
        com    = p.get("comissao_pct") or 0
        url    = p["afiliado_url"]
        img    = p.get("imagem_url")
        cat    = p.get("categoria", "game")

        emoji = "🎮" if cat == "game" else "🎧"
        preco_txt = f"💰 <b>R$ {float(preco):.2f}</b>\n" if preco else ""
        plat_txt  = f"🕹️ {plat}\n" if plat else ""

        texto = (
            f"{emoji} <b>{titulo}</b>\n"
            f"{preco_txt}"
            f"{plat_txt}"
            f"📦 Produto físico — Mercado Livre\n\n"
            f"🛒 <a href='{url}'>COMPRAR AGORA</a>\n\n"
            f"🎮 <a href='{APP}'>GamePrice Brasil</a>\n"
            f"#mercadolivre #games #{plat.lower().replace(' ','')}"
        )

        if enviar(texto, img):
            postados += 1
            # Marcar como postado agora (para rodízio)
            try:
                sb.table("ml_afiliados").update(
                    {"ultimo_post_tg": datetime.now(timezone.utc).isoformat()}
                ).eq("id", p["id"]).execute()
            except Exception as e:
                print(f"  [update] erro: {e}")
            print(f"  ✓ Postado: {titulo[:40]}")
            time.sleep(3)

    print(f"=== {postados} produtos ML postados ===")


if __name__ == "__main__":
    run()
