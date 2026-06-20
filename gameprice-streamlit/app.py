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
MEDALHAS    = {0: "🥇", 1: "🥈", 2: "🥉"}
GENEROS     = [
    "Todos", "Ação", "RPG", "FPS", "Aventura", "Indie", "Roguelike",
    "Survival", "Estratégia", "Simulação", "Multiplayer", "Horror",
    "Luta", "Esportes", "Corrida", "Plataforma",
]

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0e0e1a; }
[data-testid="stHeader"] { background: transparent; }
.game-card {
    background: #1a1a2e; border-radius: 12px;
    padding: 0; overflow: hidden;
    border: 1px solid #2a2a3e;
    transition: transform 0.2s;
    cursor: pointer;
}
.game-card:hover { border-color: #e94560; }
.card-info { padding: 8px 10px 10px; }
.card-title { font-size: 0.82rem; font-weight: 600;
    color: #e0e0e0; margin: 0 0 4px; line-height: 1.2; }
.card-price { font-size: 0.95rem; font-weight: 700; color: #e94560; }
.card-discount { background: #e94560; color: white;
    font-size: 0.7rem; font-weight: 700; padding: 2px 6px;
    border-radius: 4px; margin-left: 6px; }
.card-platform { font-size: 0.7rem; color: #888; margin-top: 2px; }
.section-title { color: #e0e0e0; font-size: 1.3rem;
    font-weight: 700; margin: 16px 0 8px; }
</style>
""", unsafe_allow_html=True)


# ── Cliente Supabase ──────────────────────────────────────────────────────────
@st.cache_resource
def get_client() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])

sb = get_client()


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_preco(valor) -> str:
    if valor is None: return "-"
    if float(valor) == 0.0: return "🆓 Gratuito"
    return f"R$ {float(valor):.2f}"


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def buscar_jogos(termo: str, plataforma: str) -> list[dict]:
    q = sb.table("games").select("id, title, slug, platform, cover_url")
    if termo:
        q = q.ilike("title", f"%{termo}%")
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    return q.order("title").limit(200).execute().data


@st.cache_data(ttl=300)
def total_jogos() -> int:
    return len(sb.table("games").select("id").execute().data)


@st.cache_data(ttl=300)
def jogos_com_desconto(limite: int = 12) -> list[dict]:
    return (
        sb.table("v_game_offers")
        .select("game_id,title,slug,platform,cover_url,store,price,discount_percent")
        .gt("discount_percent", 0)
        .order("discount_percent", desc=True)
        .limit(limite)
        .execute().data
    )


@st.cache_data(ttl=300)
def jogos_mais_baratos(plataforma: str = "Todas", limite: int = 48) -> list[dict]:
    q = (
        sb.table("v_game_offers")
        .select("game_id,title,slug,platform,cover_url,store,price,discount_percent")
        .gt("price", 0)
        .order("price", desc=False)
        .limit(limite)
    )
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    return q.execute().data


@st.cache_data(ttl=300)
def catalogo_completo(plataforma: str = "Todas") -> list[dict]:
    """Todos os jogos com o menor preco atual."""
    q = (
        sb.table("v_game_offers")
        .select("game_id,title,slug,platform,cover_url,price,discount_percent")
        .order("title")
        .limit(500)
    )
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    rows = q.execute().data
    # Deduplica: mantém só o menor preço por game_id
    visto: dict = {}
    for r in rows:
        gid = r["game_id"]
        if gid not in visto or (r.get("price") or 9999) < (visto[gid].get("price") or 9999):
            visto[gid] = r
    return sorted(visto.values(), key=lambda x: x.get("title",""))


@st.cache_data(ttl=300)
def ofertas_do_jogo(game_id: str) -> list[dict]:
    return (
        sb.table("v_game_offers").select("*")
        .eq("game_id", game_id).execute().data
    )


@st.cache_data(ttl=300)
def historico_do_jogo(offer_ids: list[str]) -> list[dict]:
    if not offer_ids: return []
    return (
        sb.table("prices")
        .select("offer_id,price,captured_at")
        .in_("offer_id", offer_ids)
        .order("captured_at").execute().data
    )


def link_afiliado(url: str, codigo: str | None) -> str:
    if not codigo: return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={codigo}"


def registrar_alerta(email: str, game_id: str, alvo: float) -> None:
    sb.table("alerts").insert(
        {"user_email": email, "game_id": game_id, "target_price": alvo}
    ).execute()


# ── HEADER ────────────────────────────────────────────────────────────────────
st.title("🎮 GamePrice Brasil")
st.caption("Compare preços de jogos em várias lojas e acompanhe o histórico.")

# ── NAVEGAÇÃO ─────────────────────────────────────────────────────────────────
aba = st.radio(
    "Navegar",
    ["🏠 Início", "📚 Catálogo", "🔍 Buscar"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# ABA: INÍCIO
# ══════════════════════════════════════════════════════════════════════════════
if aba == "🏠 Início":

    # Destaques: maiores descontos
    st.markdown('<div class="section-title">🔥 Maiores descontos agora</div>',
                unsafe_allow_html=True)
    destaques = jogos_com_desconto(12)

    if destaques:
        cols = st.columns(6)
        for i, j in enumerate(destaques[:12]):
            with cols[i % 6]:
                if j.get("cover_url"):
                    st.image(j["cover_url"], use_container_width=True)
                preco = float(j.get("price") or 0)
                pct   = j.get("discount_percent", 0)
                st.markdown(
                    f'<div class="card-info">'
                    f'<div class="card-title">{j["title"]}</div>'
                    f'<div class="card-price">{fmt_preco(preco)}'
                    f'<span class="card-discount">-{pct}%</span></div>'
                    f'<div class="card-platform">{j["platform"]} · {j["store"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver", key=f"dest_{j['game_id']}_{i}",
                             use_container_width=True):
                    st.session_state["jogo_id"]  = j["game_id"]
                    st.session_state["aba_forcar"] = "🔍 Buscar"
                    st.rerun()
    else:
        st.info("Execute o worker para carregar os preços "
                "(GitHub → Actions → update-prices → Run workflow).")

    st.divider()

    # Mais baratos por plataforma
    st.markdown('<div class="section-title">💰 Jogos mais baratos</div>',
                unsafe_allow_html=True)
    plat_home = st.selectbox("Filtrar por plataforma",
                             PLATAFORMAS, key="plat_home")
    baratos = jogos_mais_baratos(plat_home, 12)

    if baratos:
        cols = st.columns(6)
        for i, j in enumerate(baratos[:12]):
            with cols[i % 6]:
                if j.get("cover_url"):
                    st.image(j["cover_url"], use_container_width=True)
                preco = float(j.get("price") or 0)
                st.markdown(
                    f'<div class="card-info">'
                    f'<div class="card-title">{j["title"]}</div>'
                    f'<div class="card-price">{fmt_preco(preco)}</div>'
                    f'<div class="card-platform">{j["platform"]} · {j["store"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver", key=f"bar_{j['game_id']}_{i}",
                             use_container_width=True):
                    st.session_state["jogo_id"]  = j["game_id"]
                    st.session_state["aba_forcar"] = "🔍 Buscar"
                    st.rerun()

    st.divider()
    total = total_jogos()
    st.caption(f"📊 {total} jogos no catálogo · Preços atualizados a cada 6h via Steam")


# ══════════════════════════════════════════════════════════════════════════════
# ABA: CATÁLOGO
# ══════════════════════════════════════════════════════════════════════════════
elif aba == "📚 Catálogo":

    c1, c2, c3 = st.columns([2, 1, 1])
    filtro_nome = c1.text_input("🔍 Filtrar por nome", key="cat_nome",
                                placeholder="ex.: Elden, Mario...")
    filtro_plat = c2.selectbox("Plataforma", PLATAFORMAS, key="cat_plat")
    ordenar     = c3.selectbox("Ordenar por",
                               ["A-Z", "Menor preço", "Maior desconto"],
                               key="cat_ord")

    jogos = catalogo_completo(filtro_plat)

    # Filtro por nome (local, ja tem os dados)
    if filtro_nome:
        jogos = [j for j in jogos
                 if filtro_nome.lower() in j.get("title","").lower()]

    # Ordenação
    if ordenar == "Menor preço":
        jogos = sorted(jogos, key=lambda x: float(x.get("price") or 9999))
    elif ordenar == "Maior desconto":
        jogos = sorted(jogos,
                       key=lambda x: x.get("discount_percent") or 0, reverse=True)

    st.caption(f"{len(jogos)} jogos encontrados")

    if not jogos:
        st.warning("Nenhum jogo encontrado. Tente outro filtro.")
        st.stop()

    # Grid: 6 colunas
    cols_per_row = 6
    for row_start in range(0, len(jogos), cols_per_row):
        row_jogos = jogos[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for ci, j in enumerate(row_jogos):
            with cols[ci]:
                if j.get("cover_url"):
                    st.image(j["cover_url"], use_container_width=True)
                preco = float(j.get("price") or 0)
                pct   = j.get("discount_percent") or 0
                disc  = (f'<span class="card-discount">-{pct}%</span>'
                         if pct > 0 else "")
                st.markdown(
                    f'<div class="card-info">'
                    f'<div class="card-title">{j["title"]}</div>'
                    f'<div class="card-price">{fmt_preco(preco)}{disc}</div>'
                    f'<div class="card-platform">{j["platform"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver", key=f"cat_{j['game_id']}_{row_start}_{ci}",
                             use_container_width=True):
                    st.session_state["jogo_id"]  = j["game_id"]
                    st.session_state["aba_forcar"] = "🔍 Buscar"
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ABA: BUSCAR / DETALHE
# ══════════════════════════════════════════════════════════════════════════════
else:
    # Se veio de um clique de card, pre-carrega o jogo
    jogo_pre = None
    if "jogo_id" in st.session_state:
        ofertas_pre = ofertas_do_jogo(st.session_state["jogo_id"])
        if ofertas_pre:
            # Busca o jogo pelo game_id
            g = sb.table("games").select("*")\
                   .eq("id", st.session_state["jogo_id"]).execute().data
            if g:
                jogo_pre = g[0]

    c1, c2, c3 = st.columns([3, 1, 0.7])
    termo    = c1.text_input("🔍 Buscar jogo",
                             placeholder="ex.: Elden Ring, Hades...",
                             key="busca_termo")
    plat_b   = c2.selectbox("Plataforma", PLATAFORMAS, key="busca_plat")
    c3.markdown("<br>", unsafe_allow_html=True)
    c3.button("Buscar", use_container_width=True, type="primary")

    # Limpa jogo pre-carregado se o usuario digitou algo
    if termo:
        st.session_state.pop("jogo_id", None)
        jogo_pre = None

    if not termo and jogo_pre is None:
        st.info("Digite o nome de um jogo ou navegue pelo Catálogo e clique em 'Ver'.")
        st.stop()

    # Busca
    if termo:
        jogos = buscar_jogos(termo, plat_b)
        if not jogos:
            st.warning("Nenhum jogo encontrado.")
            st.stop()
        titulos = {f"{j['title']}  ({j['platform']})": j for j in jogos}
        if len(jogos) == 1:
            jogo = jogos[0]
        else:
            st.caption(f"{len(jogos)} resultado(s)")
            escolha = st.selectbox("Selecione", list(titulos.keys()))
            jogo = titulos[escolha]
    else:
        jogo = jogo_pre

    st.divider()

    # ── Detalhe ──────────────────────────────────────────────────────────────
    esq, dir_ = st.columns([1, 2])

    with esq:
        if jogo.get("cover_url"):
            st.image(jogo["cover_url"], use_container_width=True)
        st.subheader(jogo["title"])
        st.write(f"**Plataforma:** {jogo['platform']}")
        st.caption(f"slug: {jogo['slug']}")

    with dir_:
        ofertas = [o for o in ofertas_do_jogo(jogo["id"])
                   if o.get("price") is not None]
        ofertas.sort(key=lambda o: float(o["price"]))

        if not ofertas:
            st.warning("Ainda não há preços para este jogo. "
                       "Aguarde o próximo ciclo do worker (6h).")
        else:
            menor = float(ofertas[0]["price"])

            m1, m2, m3 = st.columns(3)
            m1.metric("💰 Menor preço", fmt_preco(menor))
            if ofertas[0].get("old_price") and float(ofertas[0]["old_price"]) > 0:
                economia = float(ofertas[0]["old_price"]) - menor
                m2.metric("💸 Economia", fmt_preco(economia))
            if ofertas[0].get("discount_percent"):
                m3.metric("🏷️ Desconto", f"{ofertas[0]['discount_percent']}%")

            st.markdown("### 🏆 Ranking de preços")
            linhas = []
            for i, o in enumerate(ofertas):
                preco    = float(o["price"])
                diff     = preco - menor
                diff_pct = (diff / menor * 100) if menor > 0 else 0
                linhas.append({
                    "":         MEDALHAS.get(i, f"{i+1}º"),
                    "Loja":     o["store"],
                    "Preço":    fmt_preco(preco),
                    "Desconto": f"{o['discount_percent']}%"
                                if o.get("discount_percent") else "-",
                    "vs. menor": "✅ menor preço" if diff == 0
                                 else f"+R$ {diff:.2f} ({diff_pct:.0f}%)",
                })
            st.dataframe(pd.DataFrame(linhas),
                         hide_index=True, use_container_width=True)

            for o in ofertas:
                url   = link_afiliado(o["product_url"], o.get("affiliate_code"))
                preco = float(o["price"])
                label = (f"🆓 Jogar de graça na {o['store']}" if preco == 0
                         else f"🛒 Comprar na {o['store']} — {fmt_preco(preco)}")
                st.link_button(label, url, use_container_width=True)

            st.markdown("### 📈 Histórico de preços")
            mapa_loja = {o["offer_id"]: o["store"] for o in ofertas}
            hist = historico_do_jogo(list(mapa_loja.keys()))
            if hist:
                df = pd.DataFrame(hist)
                df["captured_at"] = pd.to_datetime(df["captured_at"])
                df["Loja"]  = df["offer_id"].map(mapa_loja)
                df["price"] = df["price"].astype(float)
                df_g = df[df["price"] > 0]
                if not df_g.empty:
                    pivot = df_g.pivot_table(
                        index="captured_at", columns="Loja",
                        values="price", aggfunc="last")
                    st.line_chart(pivot)
                else:
                    st.caption("Jogo gratuito — sem histórico de preço.")
            else:
                st.caption("Histórico disponível após a primeira coleta.")

    st.divider()
    with st.expander("🔔 Criar alerta de preço"):
        st.write(f"Avise quando **{jogo['title']}** cair abaixo de um valor.")
        c1, c2 = st.columns(2)
        email   = c1.text_input("Seu e-mail", key="alert_email")
        sugestao = round(menor * 0.8, 2) if (ofertas and menor > 0) else 150.0
        alvo    = c2.number_input("Preço alvo (R$)",
                                  min_value=1.0, value=sugestao, step=10.0)
        if st.button("🔔 Criar alerta", type="primary"):
            if email and "@" in email:
                registrar_alerta(email, jogo["id"], float(alvo))
                st.success(f"✅ Alerta criado! Você será avisado quando "
                           f"{jogo['title']} ficar abaixo de {fmt_preco(alvo)}.")
            else:
                st.error("Informe um e-mail válido.")
