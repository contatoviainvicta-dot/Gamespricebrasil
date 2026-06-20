"""GamePrice Brasil - comparador de precos de jogos (Streamlit + Supabase)."""
import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="GamePrice Brasil", page_icon="🎮", layout="wide")

PLATAFORMAS = ["Todas", "PC", "PS4", "PS5", "XBOX", "SWITCH"]
MEDALHAS = {0: "🥇", 1: "🥈", 2: "🥉"}


@st.cache_resource
def get_client() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])


sb = get_client()


@st.cache_data(ttl=300)
def buscar_jogos(termo: str, plataforma: str) -> list[dict]:
    q = sb.table("games").select("*")
    if termo:
        q = q.ilike("title", f"%{termo}%")
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    return q.order("title").limit(50).execute().data


@st.cache_data(ttl=300)
def ofertas_do_jogo(game_id: str) -> list[dict]:
    return (
        sb.table("v_game_offers")
        .select("*")
        .eq("game_id", game_id)
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def historico_do_jogo(offer_ids: list[str]) -> list[dict]:
    if not offer_ids:
        return []
    return (
        sb.table("prices")
        .select("offer_id, price, captured_at")
        .in_("offer_id", offer_ids)
        .order("captured_at")
        .execute()
        .data
    )


def link_afiliado(url: str, codigo: str | None) -> str:
    if not codigo:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={codigo}"


def registrar_alerta(email: str, game_id: str, alvo: float) -> None:
    sb.table("alerts").insert(
        {"user_email": email, "game_id": game_id, "target_price": alvo}
    ).execute()


# ------------------------------------------------------------------
st.title("🎮 GamePrice Brasil")
st.caption("Compare precos de jogos em varias lojas e acompanhe o historico.")

col_busca, col_plat = st.columns([3, 1])
termo = col_busca.text_input("Buscar jogo", placeholder="ex.: Elden Ring")
plataforma = col_plat.selectbox("Plataforma", PLATAFORMAS)

jogos = buscar_jogos(termo, plataforma)

if not jogos:
    st.info("Nenhum jogo encontrado. Tente outro termo ou rode o seed.sql no Supabase.")
    st.stop()

titulos = {f"{j['title']}  ({j['platform']})": j for j in jogos}
escolha = st.selectbox("Resultados", list(titulos.keys()))
jogo = titulos[escolha]

st.divider()
esq, dir_ = st.columns([1, 2])

with esq:
    if jogo.get("cover_url"):
        st.image(jogo["cover_url"], use_container_width=True)
    st.subheader(jogo["title"])
    st.write(f"Plataforma: **{jogo['platform']}**")
    st.caption(f"slug: {jogo['slug']}")

with dir_:
    ofertas = [o for o in ofertas_do_jogo(jogo["id"]) if o.get("price") is not None]
    ofertas.sort(key=lambda o: float(o["price"]))

    if not ofertas:
        st.warning("Ainda nao ha precos para este jogo. Rode o worker para coletar.")
    else:
        menor = float(ofertas[0]["price"])
        st.metric("Menor preco", f"R$ {menor:.2f}")

        st.markdown("### Ranking de precos")
        linhas = []
        for i, o in enumerate(ofertas):
            preco = float(o["price"])
            diff = preco - menor
            diff_pct = (diff / menor * 100) if menor else 0
            linhas.append(
                {
                    "": MEDALHAS.get(i, f"{i + 1}º"),
                    "Loja": o["store"],
                    "Preco": f"R$ {preco:.2f}",
                    "Desconto": f"{o['discount_percent']}%" if o.get("discount_percent") else "-",
                    "vs. menor": "menor preco" if diff == 0 else f"+R$ {diff:.2f} ({diff_pct:.0f}%)",
                }
            )
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

        for o in ofertas:
            url = link_afiliado(o["product_url"], o.get("affiliate_code"))
            st.link_button(f"Ver na {o['store']} - R$ {float(o['price']):.2f}", url)

        # ----- Historico -----
        st.markdown("### Historico de precos")
        mapa_loja = {o["offer_id"]: o["store"] for o in ofertas}
        hist = historico_do_jogo(list(mapa_loja.keys()))
        if hist:
            df = pd.DataFrame(hist)
            df["captured_at"] = pd.to_datetime(df["captured_at"])
            df["Loja"] = df["offer_id"].map(mapa_loja)
            df["price"] = df["price"].astype(float)
            pivot = df.pivot_table(
                index="captured_at", columns="Loja", values="price", aggfunc="last"
            )
            st.line_chart(pivot)
        else:
            st.caption("Sem historico ainda - os pontos aparecem conforme o worker roda.")

# ------------------------------------------------------------------
st.divider()
with st.expander("🔔 Criar alerta de preco"):
    st.write(f"Avise quando **{jogo['title']}** ficar abaixo de um valor.")
    c1, c2 = st.columns(2)
    email = c1.text_input("Seu e-mail", key="alert_email")
    alvo = c2.number_input("Preco alvo (R$)", min_value=1.0, value=150.0, step=10.0)
    if st.button("Criar alerta"):
        if email and "@" in email:
            registrar_alerta(email, jogo["id"], float(alvo))
            st.success("Alerta criado! Voce sera avisado quando o preco cair.")
        else:
            st.error("Informe um e-mail valido.")
