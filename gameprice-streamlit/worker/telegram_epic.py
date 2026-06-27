"""Post semanal: jogos grátis da Epic Games.

Roda 1x por semana (quinta, quando a Epic troca os grátis).
Posts de jogos grátis têm altíssimo engajamento.
"""
import os
import httpx
from supabase import create_client

URL   = os.environ["SUPABASE_URL"]
KEY   = os.environ["SUPABASE_SERVICE_KEY"]
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT  = os.environ["TELEGRAM_CHAT_ID"]
APP   = os.environ.get("APP_URL", "https://gameprice.streamlit.app")


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
                data={"chat_id": CHAT, "text": texto, "parse_mode": "HTML"},
                timeout=20,
            )
        return r.status_code == 200
    except Exception as e:
        print(f"  [telegram] exceção: {e}")
        return False


def run():
    sb = create_client(URL, KEY)
    print("=== Jogos grátis da Epic ===")

    try:
        r = sb.table("epic_free_games").select("current,next").eq("id", 1).execute().data
        ep = r[0] if r else {}
    except Exception:
        ep = {}

    atuais = ep.get("current", [])
    proximos = ep.get("next", [])

    if not atuais:
        print("Sem jogos grátis no momento.")
        return

    linhas = ["🎁 <b>JOGOS GRÁTIS NA EPIC ESTA SEMANA</b>\n"]
    for g in atuais:
        linhas.append(f"✅ <b>{g['title']}</b> — GRÁTIS agora!")
    if proximos:
        linhas.append("\n🔜 <b>Em breve:</b>")
        for g in proximos:
            linhas.append(f"   • {g['title']}")
    linhas.append("\n🔗 <a href='https://store.epicgames.com/pt-BR/free-games'>Pegar na Epic</a>")
    linhas.append(f"🎮 <a href='{APP}'>GamePrice Brasil</a>")
    linhas.append("#epicgames #jogosgratis #freegames")

    texto = "\n".join(linhas)
    # Tentar com imagem do primeiro jogo
    img = atuais[0].get("image_url") if atuais else None
    if enviar(texto, img):
        print(f"  ✓ Post Epic com {len(atuais)} jogos grátis")
    else:
        print("  ✗ Falha ao postar")


if __name__ == "__main__":
    run()
