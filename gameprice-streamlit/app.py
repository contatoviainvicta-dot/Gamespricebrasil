"""GamePrice Brasil - comparador de precos de jogos (Streamlit + Supabase)."""
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from supabase import Client, create_client

st.set_page_config(
    page_title="GamePrice Brasil 🎮",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PLATAFORMAS = ["Todas", "PC", "PS4", "PS5", "XBOX", "SWITCH"]
MEDALHAS    = {0: "🥇", 1: "🥈", 2: "🥉"}

st.markdown("""
<style>
.card-title {
    font-size: 0.85rem; font-weight: 600;
    color: #1a1a2e; margin: 4px 0 2px; line-height: 1.3;
}
.card-price { font-size: 0.95rem; font-weight: 700; color: #e94560; }
.card-discount {
    background: #e94560; color: white;
    font-size: 0.7rem; font-weight: 700;
    padding: 1px 5px; border-radius: 4px; margin-left: 5px;
}
.card-platform { font-size: 0.72rem; color: #666; margin-top: 2px; }
.epic-free-card {
    background: linear-gradient(135deg, #2d0080 0%, #6600cc 100%);
    border-radius: 12px; padding: 12px; color: white; text-align: center;
}
.epic-free-title { font-size: 0.9rem; font-weight: 700; margin: 6px 0 2px; }
.epic-free-badge {
    background: #00d4aa; color: #000;
    font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 20px; display: inline-block;
}
.epic-next-badge {
    background: #ff6b35; color: white;
    font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 20px; display: inline-block;
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_client() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])

sb = get_client()


def fmt_preco(valor) -> str:
    if valor is None: return "-"
    if float(valor) == 0.0: return "🆓 Gratuito"
    return f"R$ {float(valor):.2f}"


def fmt_data(iso: str) -> str:
    """Converte ISO date para formato legível."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d/%m às %H:%Mh")
    except Exception:
        return iso[:10]


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def buscar_jogos(termo: str, plataforma: str) -> list[dict]:
    q = sb.table("games").select("id,title,slug,platform,cover_url")
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
def jogos_mais_baratos(plataforma: str = "Todas", limite: int = 12) -> list[dict]:
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
    q = (
        sb.table("v_game_offers")
        .select("game_id,title,slug,platform,cover_url,price,discount_percent")
        .order("title").limit(500)
    )
    if plataforma != "Todas":
        q = q.eq("platform", plataforma)
    rows = q.execute().data
    visto: dict = {}
    for r in rows:
        gid  = r["game_id"]
        p    = float(r.get("price") or 9999)
        pant = float(visto[gid].get("price") or 9999) if gid in visto else 9999
        if gid not in visto or p < pant:
            visto[gid] = r
    return sorted(visto.values(), key=lambda x: x.get("title", ""))


@st.cache_data(ttl=1800)  # 30 min — muda só quinta-feira
def epic_free_games() -> dict:
    """Lê jogos gratuitos da Epic salvos pelo worker."""
    try:
        r = sb.table("epic_free_games").select("current,next,updated_at")\
               .eq("id", 1).execute().data
        if r:
            return r[0]
    except Exception:
        pass
    return {"current": [], "next": [], "updated_at": None}


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


def card_jogo(j: dict, key_prefix: str, idx: int) -> None:
    if j.get("cover_url"):
        st.image(j["cover_url"], use_container_width=True)
    preco = float(j.get("price") or 0)
    pct   = j.get("discount_percent") or 0
    disc  = f'<span class="card-discount">-{pct}%</span>' if pct > 0 else ""
    st.markdown(
        f'<div class="card-title">{j["title"]}</div>'
        f'<div class="card-price">{fmt_preco(preco)}{disc}</div>'
        f'<div class="card-platform">{j.get("platform","")} '
        f'{("· " + j["store"]) if j.get("store") else ""}</div>',
        unsafe_allow_html=True,
    )
    if st.button("Ver detalhes", key=f"{key_prefix}_{j['game_id']}_{idx}",
                 use_container_width=True):
        st.session_state["jogo_id"] = j["game_id"]
        st.session_state["ir_busca"] = True
        st.rerun()


# ── HEADER ────────────────────────────────────────────────────────────────────
st.title("🎮 GamePrice Brasil")
st.caption("Compare preços de jogos em várias lojas e acompanhe o histórico.")

if st.session_state.get("ir_busca"):
    st.session_state.pop("ir_busca", None)
    aba_default = 2
else:
    aba_default = 0

aba = st.radio(
    "Navegar",
    ["🏠 Início", "📚 Catálogo", "🔍 Buscar"],
    horizontal=True,
    label_visibility="collapsed",
    index=aba_default,
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# ABA: INÍCIO
# ══════════════════════════════════════════════════════════════════════════════
if aba == "🏠 Início":

    # ── Jogos gratuitos da Epic ───────────────────────────────────────────────
    epic = epic_free_games()
    current_free = epic.get("current", [])
    next_free    = epic.get("next", [])

    if current_free or next_free:
        st.subheader("🎁 Grátis na Epic Games")

        col_width = max(1, len(current_free) + len(next_free))
        cols = st.columns(min(col_width, 6))
        col_idx = 0

        for g in current_free:
            with cols[col_idx % 6]:
                if g.get("image_url"):
                    st.image(g["image_url"], use_container_width=True)
                end = fmt_data(g["end_date"]) if g.get("end_date") else ""
                st.markdown(
                    f'<div class="epic-free-title">{g["title"]}</div>'
                    f'<span class="epic-free-badge">🎁 GRÁTIS AGORA</span>'
                    f'{"<br><small style='color:#666'>até " + end + "</small>" if end else ""}',
                    unsafe_allow_html=True,
                )
                # Usa sempre a página de free-games como destino seguro.
                # O slug individual da API às vezes é interno e gera 404.
                epic_url = "https://store.epicgames.com/pt-BR/free-games"
                st.link_button(
                    "Pegar grátis na Epic →",
                    epic_url,
                    use_container_width=True,
                )
            col_idx += 1

        for g in next_free:
            with cols[col_idx % 6]:
                if g.get("image_url"):
                    st.image(g["image_url"], use_container_width=True)
                start = fmt_data(g["start_date"]) if g.get("start_date") else ""
                st.markdown(
                    f'<div class="epic-free-title">{g["title"]}</div>'
                    f'<span class="epic-next-badge">🔜 EM BREVE</span>'
                    f'{"<br><small style='color:#666'>a partir de " + start + "</small>" if start else ""}',
                    unsafe_allow_html=True,
                )
            col_idx += 1

        if epic.get("updated_at"):
            st.caption(f"Atualizado: {fmt_data(epic['updated_at'])}")
        st.divider()
    else:
        # Tabela não existe ainda ou worker não rodou
        st.info("🎁 Execute o SQL `epic_setup.sql` no Supabase e rode o worker "
                "para ver os jogos gratuitos da Epic aqui.")
        st.divider()

    # ── Maiores descontos ─────────────────────────────────────────────────────
    st.subheader("🔥 Maiores descontos agora")
    destaques = jogos_com_desconto(12)

    if destaques:
        cols = st.columns(6)
        for i, j in enumerate(destaques[:12]):
            with cols[i % 6]:
                card_jogo(j, "dest", i)
    else:
        st.info("Execute o worker para carregar os preços "
                "(GitHub → Actions → update-prices → Run workflow).")

    st.divider()

    # ── Mais baratos ──────────────────────────────────────────────────────────
    st.subheader("💰 Jogos mais baratos")
    plat_home = st.selectbox("Filtrar plataforma", PLATAFORMAS, key="plat_home")
    baratos   = jogos_mais_baratos(plat_home, 12)

    if baratos:
        cols = st.columns(6)
        for i, j in enumerate(baratos[:12]):
            with cols[i % 6]:
                card_jogo(j, "bar", i)

    st.divider()
    total = total_jogos()
    st.caption(f"📊 {total} jogos · Steam · Epic · Preços atualizados a cada 6h")


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

    if filtro_nome:
        jogos = [j for j in jogos
                 if filtro_nome.lower() in j.get("title", "").lower()]

    if ordenar == "Menor preço":
        jogos = sorted(jogos, key=lambda x: float(x.get("price") or 9999))
    elif ordenar == "Maior desconto":
        jogos = sorted(jogos,
                       key=lambda x: x.get("discount_percent") or 0, reverse=True)

    st.caption(f"{len(jogos)} jogos encontrados")

    if not jogos:
        st.warning("Nenhum jogo encontrado.")
        st.stop()

    for row_start in range(0, len(jogos), 6):
        cols = st.columns(6)
        for ci, j in enumerate(jogos[row_start:row_start + 6]):
            with cols[ci]:
                card_jogo(j, "cat", row_start + ci)


# ══════════════════════════════════════════════════════════════════════════════
# ABA: BUSCAR / DETALHE
# ══════════════════════════════════════════════════════════════════════════════
else:
    jogo_pre = None
    if "jogo_id" in st.session_state:
        g = sb.table("games").select("*")\
               .eq("id", st.session_state["jogo_id"]).execute().data
        if g:
            jogo_pre = g[0]

    c1, c2, c3 = st.columns([3, 1, 0.7])
    termo  = c1.text_input("🔍 Buscar jogo",
                           placeholder="ex.: Elden Ring, Hades...",
                           key="busca_termo")
    plat_b = c2.selectbox("Plataforma", PLATAFORMAS, key="busca_plat")
    c3.markdown("<br>", unsafe_allow_html=True)
    c3.button("Buscar", use_container_width=True, type="primary")

    if termo:
        st.session_state.pop("jogo_id", None)
        jogo_pre = None

    if not termo and jogo_pre is None:
        st.info("Digite o nome de um jogo ou navegue pelo **Catálogo** "
                "e clique em 'Ver detalhes'.")
        st.stop()

    if termo:
        jogos = buscar_jogos(termo, plat_b)
        if not jogos:
            st.warning("Nenhum jogo encontrado.")
            st.stop()
        titulos = {f"{j['title']}  ({j['platform']})": j for j in jogos}
        jogo = jogos[0] if len(jogos) == 1 else titulos[
            st.selectbox("Selecione", list(titulos.keys()))
        ]
    else:
        jogo = jogo_pre

    st.divider()
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
            st.warning("Ainda não há preços. Aguarde o próximo ciclo do worker (6h).")
        else:
            menor = float(ofertas[0]["price"])
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 Menor preço", fmt_preco(menor))
            if ofertas[0].get("old_price") and float(ofertas[0]["old_price"]) > 0:
                m2.metric("💸 Economia",
                          fmt_preco(float(ofertas[0]["old_price"]) - menor))
            if ofertas[0].get("discount_percent"):
                m3.metric("🏷️ Desconto", f"{ofertas[0]['discount_percent']}%")

            st.markdown("### 🏆 Ranking de preços")
            linhas = []
            for i, o in enumerate(ofertas):
                preco    = float(o["price"])
                diff     = preco - menor
                diff_pct = (diff / menor * 100) if menor > 0 else 0
                linhas.append({
                    "":          MEDALHAS.get(i, f"{i+1}º"),
                    "Loja":      o["store"],
                    "Preço":     fmt_preco(preco),
                    "Desconto":  f"{o['discount_percent']}%"
                                 if o.get("discount_percent") else "-",
                    "vs. menor": "✅ menor preço" if diff == 0
                                 else f"+R$ {diff:.2f} ({diff_pct:.0f}%)",
                })
            st.dataframe(pd.DataFrame(linhas),
                         hide_index=True, use_container_width=True)

            for o in ofertas:
                url   = link_afiliado(o["product_url"], o.get("affiliate_code"))
                preco = float(o["price"])
                loja  = o["store"]
                emoji = "🟣" if "Epic" in loja else "🟦"
                label = (f"🆓 Jogar de graça na {loja}" if preco == 0
                         else f"{emoji} Comprar na {loja} — {fmt_preco(preco)}")
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
        email    = c1.text_input("Seu e-mail", key="alert_email")
        sugestao = round(menor * 0.8, 2) if (ofertas and menor > 0) else 150.0
        alvo     = c2.number_input("Preço alvo (R$)",
                                   min_value=1.0, value=sugestao, step=10.0)
        if st.button("🔔 Criar alerta", type="primary"):
            if email and "@" in email:
                registrar_alerta(email, jogo["id"], float(alvo))
                st.success(f"✅ Alerta criado! Você será avisado quando "
                           f"{jogo['title']} ficar abaixo de {fmt_preco(alvo)}.")
            else:
                st.error("Informe um e-mail válido.")
