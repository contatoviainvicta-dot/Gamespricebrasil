"""Bot de ofertas: posta os melhores deals no canal do Telegram.

Roda após o update de preços. Detecta mínimos históricos e descontos
altos, e posta automaticamente no canal — sem intervenção manual.

Secrets necessários (GitHub Actions):
  TELEGRAM_BOT_TOKEN  → token do @BotFather
  TELEGRAM_CHAT_ID    → @seucanal (username público do canal)
  APP_URL             → URL do app (ex: https://xxx.streamlit.app)
"""
import os, time
import httpx
from supabase import create_client

URL   = os.environ["SUPABASE_URL"]
KEY   = os.environ["SUPABASE_SERVICE_KEY"]
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT  = os.environ["TELEGRAM_CHAT_ID"]
APP   = os.environ.get("APP_URL", "https://gameprice.streamlit.app")

# Critérios para postar uma oferta
DESCONTO_MIN   = 70    # só posta deals com 70%+ de desconto
MAX_POR_CICLO  = 8     # no máximo 8 posts por execução (não floodar)


def enviar_telegram(texto: str, imagem: str = None) -> bool:
    """Envia mensagem ao canal (com foto se disponível)."""
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


def ja_postado(sb, game_id: str, preco: float) -> bool:
    """Evita repostar o mesmo deal (mesmo jogo + mesmo preço)."""
    try:
        r = (sb.table("telegram_posts")
             .select("id")
             .eq("game_id", game_id)
             .eq("preco", preco)
             .execute().data)
        return len(r) > 0
    except Exception:
        return False


def marcar_postado(sb, game_id: str, preco: float):
    try:
        sb.table("telegram_posts").insert(
            {"game_id": game_id, "preco": preco}).execute()
    except Exception as e:
        print(f"  [marcar] erro: {e}")


def run() -> None:
    sb = create_client(URL, KEY)
    print("=== Bot de ofertas Telegram ===")

    # Buscar os melhores deals atuais
    deals = (sb.table("v_game_offers")
             .select("game_id,title,platform,cover_url,store,price,old_price,discount_percent")
             .gte("discount_percent", DESCONTO_MIN)
             .order("discount_percent", desc=True)
             .limit(40)
             .execute().data)

    print(f"{len(deals)} deals com {DESCONTO_MIN}%+ de desconto")

    postados = 0
    for d in deals:
        if postados >= MAX_POR_CICLO:
            break
        gid   = d["game_id"]
        preco = float(d.get("price") or 0)
        if preco <= 0:
            continue
        if ja_postado(sb, gid, preco):
            continue

        titulo   = d["title"]
        loja     = d.get("store", "")
        desc     = d.get("discount_percent", 0)
        original = float(d.get("old_price") or 0)
        capa     = d.get("cover_url")
        link     = f"{APP}"

        # Montar mensagem
        economia = ""
        if original > preco:
            economia = f"\n💸 De <s>R$ {original:.2f}</s> por <b>R$ {preco:.2f}</b>"
        else:
            economia = f"\n💰 <b>R$ {preco:.2f}</b>"

        texto = (
            f"🔥 <b>{titulo}</b>\n"
            f"🏷️ <b>-{desc}%</b> na {loja}"
            f"{economia}\n"
            f"🎮 {d.get('platform','PC')}\n\n"
            f"🔗 <a href='{link}'>Ver no GamePrice Brasil</a>\n"
            f"#oferta #games #{loja.lower().replace(' ','')}"
        )

        if enviar_telegram(texto, capa):
            marcar_postado(sb, gid, preco)
            postados += 1
            print(f"  ✓ Postado: {titulo[:40]} (-{desc}%)")
            time.sleep(3)  # Pausa entre posts (limite do Telegram)

    print(f"=== {postados} ofertas postadas ===")


if __name__ == "__main__":
    run()
