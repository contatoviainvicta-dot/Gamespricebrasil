"""GamePrice Brasil - comparador de precos de jogos (Streamlit + Supabase)."""
import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(
    page_title="GamePrice Brasil 🎮",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PLATAFORMAS = ["Todas", "PC", "PS4", "PS5", "XBOX", "SWITCH"]
MEDALHAS = {0: "🥇", 1: "🥈", 2: "🥉"}

st.markdown("""
<style>
.price-badge {
    background: #1a1a2e; color: #e94560;
    padding: 4px 12px; border-radius: 20px;
    font-size: 1.4rem; font-weight: bold;
}
.store-card {
    background: #16213e; padding: 12px;
    border-radius: 10px; margin: 4px 0;
    border-left: 4px solid #e94560;
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_client() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])

sb = get_client()


def fmt_preco(valor) -> str:
    """Formata preco: zero vira Gratuito, resto vira R$ X,XX."""
    if valor is None:
        return "-"
    if float(valor) == 0.0:
        return "🆓 Gratuito"
    return f"R$ {float(valor):.2f}"


@st.cache_data(ttl=300)
def buscar_jogos(termo: str, plataforma: str) -> list[dict]:
    q = sb.table("games").select("id, title, slug, platform, cover_url")
    if termo:
        q = q.ilike("title", f"%{termo}%")
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    return q.order("title").limit(100).execute().data


@st.cache_data(ttl=300)
def total_jogos() -> int:
    return len(sb.table("games").select("id").execute().data)


@st.cache_data(ttl=300)
def jogos_mais_baratos() -> list[dict]:
    """Jogos com maior desconto atual via view v_game_offers."""
    return (
        sb.table("v_game_offers")
        .select("game_id, title, slug, platform, cover_url, store, price, discount_percent")
        .gt("discount_percent", 0)
        .order("discount_percent", desc=True)
        .limit(8)
        .execute()
        .data
    )


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


# ── HEADER ──────────────────────────────────────────────────────────────────
st.title("🎮 GamePrice Brasil")
st.caption("Compare preços de jogos em várias lojas e acompanhe o histórico.")

# ── BUSCA ───────────────────────────────────────────────────────────────────
col_busca, col_plat, col_btn = st.columns([3, 1, 0.7])
termo = col_busca.text_input("🔍 Buscar jogo", placeholder="ex.: Elden Ring, Hades...")
plataforma = col_plat.selectbox("Plataforma", PLATAFORMAS)
col_btn.markdown("<br>", unsafe_allow_html=True)
col_btn.button("Buscar", use_container_width=True, type="primary")

# ── PAGINA INICIAL ──────────────────────────────────────────────────────────
if not termo:
    st.divider()
    st.subheader("🔥 Maiores descontos agora")
    baratos = jogos_mais_baratos()

    if baratos:
        cols = st.columns(4)
        for i, jogo in enumerate(baratos):
            with cols[i % 4]:
                if jogo.get("cover_url"):
                    st.image(jogo["cover_url"], use_container_width=True)
                pct  = jogo.get("discount_percent", 0)
                preco = float(jogo.get("price") or 0)
                st.markdown(f"**{jogo['title']}**")
                st.markdown(
                    f"<span style='color:#e94560;font-weight:bold'>-{pct}%</span> "
                    f"{fmt_preco(preco)}",
                    unsafe_allow_html=True,
                )
                if st.button("Ver detalhes", key=f"btn_{jogo['game_id']}_{i}"):
                    st.session_state["jogo_id"] = jogo["game_id"]
                    st.rerun()
    else:
        st.info("Execute o worker para carregar os preços da Steam "
                "(GitHub → Actions → update-prices → Run workflow).")

    st.divider()
    st.subheader(f"📚 Catálogo ({total_jogos()} jogos)")
    st.caption("Use a busca acima para encontrar um jogo específico.")
    st.stop()

# ── RESULTADOS DA BUSCA ─────────────────────────────────────────────────────
jogos = buscar_jogos(termo, plataforma)
if not jogos:
    st.warning("Nenhum jogo encontrado. Tente outro termo.")
    st.stop()

st.divider()
titulos = {f"{j['title']}  ({j['platform']})": j for j in jogos}

if len(jogos) == 1:
    jogo = jogos[0]
else:
    st.caption(f"{len(jogos)} resultado(s) encontrado(s)")
    escolha = st.selectbox("Selecione o jogo", list(titulos.keys()))
    jogo = titulos[escolha]

# ── DETALHE DO JOGO ─────────────────────────────────────────────────────────
esq, dir_ = st.columns([1, 2])

with esq:
    if jogo.get("cover_url"):
        st.image(jogo["cover_url"], use_container_width=True)
    st.subheader(jogo["title"])
    st.write(f"**Plataforma:** {jogo['platform']}")
    st.caption(f"slug: {jogo['slug']}")

with dir_:
    ofertas = [o for o in ofertas_do_jogo(jogo["id"]) if o.get("price") is not None]
    ofertas.sort(key=lambda o: float(o["price"]))

    if not ofertas:
        st.warning("Ainda não há preços para este jogo. "
                   "Aguarde o próximo ciclo do worker (6h).")
    else:
        menor = float(ofertas[0]["price"])

        # ── Metricas ──
        m1, m2, m3 = st.columns(3)
        m1.metric("💰 Menor preço", fmt_preco(menor))

        if ofertas[0].get("old_price") and float(ofertas[0]["old_price"]) > 0:
            economia = float(ofertas[0]["old_price"]) - menor
            m2.metric("💸 Economia", fmt_preco(economia))

        if ofertas[0].get("discount_percent"):
            m3.metric("🏷️ Desconto", f"{ofertas[0]['discount_percent']}%")

        # ── Ranking ──
        st.markdown("### 🏆 Ranking de preços")
        linhas = []
        for i, o in enumerate(ofertas):
            preco   = float(o["price"])
            diff    = preco - menor
            diff_pct = (diff / menor * 100) if menor > 0 else 0
            linhas.append({
                "":         MEDALHAS.get(i, f"{i+1}º"),
                "Loja":     o["store"],
                "Preço":    fmt_preco(preco),
                "Desconto": f"{o['discount_percent']}%" if o.get("discount_percent") else "-",
                "vs. menor": "✅ menor preço" if diff == 0
                             else f"+R$ {diff:.2f} ({diff_pct:.0f}%)",
            })
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

        for o in ofertas:
            url   = link_afiliado(o["product_url"], o.get("affiliate_code"))
            preco = float(o["price"])
            label = (f"🆓 Jogar de graça na {o['store']}" if preco == 0
                     else f"🛒 Comprar na {o['store']} — {fmt_preco(preco)}")
            st.link_button(label, url, use_container_width=True)

        # ── Historico ──
        st.markdown("### 📈 Histórico de preços")
        mapa_loja = {o["offer_id"]: o["store"] for o in ofertas}
        hist = historico_do_jogo(list(mapa_loja.keys()))

        if hist:
            df = pd.DataFrame(hist)
            df["captured_at"] = pd.to_datetime(df["captured_at"])
            df["Loja"]  = df["offer_id"].map(mapa_loja)
            df["price"] = df["price"].astype(float)
            # Filtra gratuitos do grafico (preco 0 distorce a escala)
            df_grafico = df[df["price"] > 0]
            if not df_grafico.empty:
                pivot = df_grafico.pivot_table(
                    index="captured_at", columns="Loja",
                    values="price", aggfunc="last"
                )
                st.line_chart(pivot)
            else:
                st.caption("Jogo gratuito — sem histórico de preço para exibir.")
        else:
            st.caption("Histórico disponível após a primeira coleta do worker.")

# ── ALERTA ──────────────────────────────────────────────────────────────────
st.divider()
with st.expander("🔔 Criar alerta de preço"):
    st.write(f"Avise quando **{jogo['title']}** cair abaixo de um valor.")
    c1, c2 = st.columns(2)
    email = c1.text_input("Seu e-mail", key="alert_email")
    sugestao = round(menor * 0.8, 2) if (ofertas and menor > 0) else 150.0
    alvo = c2.number_input("Preço alvo (R$)", min_value=1.0, value=sugestao, step=10.0)
    if st.button("🔔 Criar alerta", type="primary"):
        if email and "@" in email:
            registrar_alerta(email, jogo["id"], float(alvo))
            st.success(f"✅ Alerta criado! Você será avisado quando "
                       f"{jogo['title']} ficar abaixo de {fmt_preco(alvo)}.")
        else:
            st.error("Informe um e-mail válido.")
