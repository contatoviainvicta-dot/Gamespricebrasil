"""GamePrice Brasil - layout inspirado no IsThereAnyDeal."""
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from supabase import Client, create_client

st.set_page_config(
    page_title="GamePrice Brasil",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar escura estilo ITAD */
[data-testid="stSidebar"] {
    background: #1b2838;
    border-right: 1px solid #2a3f5a;
}
[data-testid="stSidebar"] * { color: #c6d4df !important; }
[data-testid="stSidebar"] .stRadio label { color: #c6d4df !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #ffffff !important; }

/* Deal card horizontal */
.deal-card {
    display: flex;
    gap: 12px;
    background: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 8px;
    align-items: flex-start;
}
.deal-cover img { width: 120px; border-radius: 4px; }
.deal-info { flex: 1; }
.deal-title {
    font-size: 1rem; font-weight: 700;
    color: #1b2838; margin-bottom: 4px;
}
.deal-platform {
    font-size: 0.75rem; color: #666;
    margin-bottom: 6px;
}
.price-row {
    display: flex; align-items: center; gap: 8px;
    flex-wrap: wrap;
}
.price-current {
    font-size: 1.2rem; font-weight: 700; color: #4c9d4c;
}
.price-original {
    font-size: 0.85rem; color: #999;
    text-decoration: line-through;
}
.badge-discount {
    background: #4c9d4c; color: white;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 7px; border-radius: 4px;
}
.badge-free {
    background: #1b74e8; color: white;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 7px; border-radius: 4px;
}
.badge-lowest {
    background: #c6430a; color: white;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 7px; border-radius: 4px;
}
.store-tag {
    font-size: 0.72rem; color: #555;
    background: #f0f2f4; padding: 2px 6px;
    border-radius: 3px;
}
/* Tabela de preços */
.price-table { width: 100%; border-collapse: collapse; }
.price-table th {
    background: #f0f2f4; text-align: left;
    padding: 6px 10px; font-size: 0.78rem;
    color: #555; border-bottom: 1px solid #ddd;
}
.price-table td {
    padding: 6px 10px; font-size: 0.85rem;
    border-bottom: 1px solid #eee; vertical-align: middle;
}
.price-table tr:hover { background: #f8f9fa; }
.rank-medal { font-size: 1.1rem; }
/* Epic free banner */
.epic-banner {
    background: linear-gradient(135deg,#1b2838 0%,#2a475e 100%);
    border-radius: 10px; padding: 14px 16px;
    margin-bottom: 8px; color: white;
    display: flex; gap: 14px; align-items: center;
}
.epic-banner-info h4 { margin: 0 0 4px; font-size: 0.95rem; }
.epic-banner-info p  { margin: 0; font-size: 0.78rem; color: #8fb4d4; }
/* Section header */
.section-header {
    font-size: 1.1rem; font-weight: 700;
    color: #1b2838; border-left: 4px solid #4c9d4c;
    padding-left: 10px; margin: 16px 0 10px;
}
</style>
""", unsafe_allow_html=True)

PLATAFORMAS = ["Todas", "PC", "PS4", "PS5", "XBOX", "SWITCH"]
LOJAS       = ["Todas", "Steam", "GOG", "Humble Store", "Epic Games",
               "Nuuvem", "Fanatical"]
MEDALHAS    = {0:"🥇", 1:"🥈", 2:"🥉"}
LOJA_CORES  = {
    "Steam":       "#1b2838",
    "GOG":         "#8a2be2",
    "Humble Store":"#cc2200",
    "Epic Games":  "#2f4f4f",
    "Nuuvem":      "#0066cc",
    "Fanatical":   "#ff4500",
}

# ── Cliente ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_sb() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])

sb = get_sb()

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_preco(v) -> str:
    if v is None: return "—"
    if float(v) == 0: return "Gratuito"
    return f"R$ {float(v):.2f}"

def fmt_data(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
        return dt.strftime("%d/%m às %H:%Mh")
    except Exception:
        return iso[:10]

# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _q(table, select="*", filters: dict | None = None,
        order=None, limit=100, desc=False):
    q = sb.table(table).select(select)
    for k,v in (filters or {}).items():
        if isinstance(v, bool):
            q = q.is_(k, str(v).lower()) if v is None else q.eq(k, v)
        elif v is not None:
            q = q.eq(k, v)
    if order:
        q = q.order(order, desc=desc)
    return q.limit(limit).execute().data

@st.cache_data(ttl=300)
def total_jogos(): return len(sb.table("games").select("id").execute().data)

@st.cache_data(ttl=300)
def jogos_com_desconto(loja="Todas", plat="Todas", min_desc=0, limite=30):
    q = (sb.table("v_game_offers")
         .select("game_id,title,slug,platform,cover_url,store,price,old_price,discount_percent")
         .gt("discount_percent", min_desc)
         .order("discount_percent", desc=True)
         .limit(limite))
    if plat != "Todas": q = q.eq("platform", plat)
    if loja != "Todas": q = q.eq("store", loja)
    return q.execute().data

@st.cache_data(ttl=300)
def buscar_jogos(termo, plat="Todas"):
    q = sb.table("games").select("id,title,slug,platform,cover_url")
    if termo: q = q.ilike("title", f"%{termo}%")
    if plat != "Todas": q = q.eq("platform", plat)
    return q.order("title").limit(100).execute().data

@st.cache_data(ttl=300)
def ofertas_jogo(game_id):
    return (sb.table("v_game_offers").select("*")
            .eq("game_id", game_id).execute().data)

@st.cache_data(ttl=300)
def historico_jogo(offer_ids):
    if not offer_ids: return []
    return (sb.table("prices")
            .select("offer_id,price,captured_at")
            .in_("offer_id", offer_ids)
            .order("captured_at").execute().data)

@st.cache_data(ttl=300)
def min_historico(offer_ids):
    """Retorna o menor preço histórico entre todas as ofertas."""
    if not offer_ids: return None
    rows = (sb.table("prices").select("price")
            .in_("offer_id", offer_ids)
            .gt("price", 0).execute().data)
    if not rows: return None
    return min(float(r["price"]) for r in rows)

@st.cache_data(ttl=1800)
def epic_free():
    try:
        r = sb.table("epic_free_games").select("current,next,updated_at")\
               .eq("id",1).execute().data
        return r[0] if r else {}
    except Exception:
        return {}

@st.cache_data(ttl=600)
def metricas():
    total_p = len(sb.table("prices").select("id").execute().data)
    lojas_r = sb.table("stores").select("id,name,slug").eq("active",True).execute().data
    contagem = []
    for l in lojas_r:
        c = len(sb.table("game_store_offers").select("id")
                .eq("store_id", l["id"]).eq("active",True).execute().data)
        if c > 0:
            contagem.append({"loja": l["name"], "ofertas": c})
    return {
        "total_jogos":  total_jogos(),
        "total_precos": total_p,
        "lojas":        sorted(contagem, key=lambda x: x["ofertas"], reverse=True),
    }

def registrar_alerta(email, game_id, alvo):
    sb.table("alerts").insert(
        {"user_email": email, "game_id": game_id, "target_price": alvo}
    ).execute()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎮 GamePrice Brasil")
    st.markdown("---")
    pagina = st.radio(
        "Navegar",
        ["🏠 Deals", "🔍 Buscar", "📚 Catálogo", "📊 Stats"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown("**Filtros**")
    filtro_plat = st.selectbox("Plataforma", PLATAFORMAS, key="sb_plat")
    filtro_loja = st.selectbox("Loja", LOJAS, key="sb_loja")
    filtro_desc = st.slider("Desconto mínimo", 0, 90, 0, 10, key="sb_desc",
                             format="%d%%")
    st.markdown("---")

    # Epic free games na sidebar
    epic = epic_free()
    current_free = epic.get("current", [])
    if current_free:
        st.markdown("**🎁 Grátis na Epic agora**")
        for g in current_free:
            st.markdown(f"• {g['title']}")
            end = fmt_data(g['end_date']) if g.get('end_date') else ""
            if end:
                st.caption(f"até {end}")
        st.link_button("Ver na Epic →",
                       "https://store.epicgames.com/pt-BR/free-games",
                       use_container_width=True)
        st.markdown("---")

    st.caption(f"📊 {total_jogos()} jogos · Steam · GOG · Humble")


# ── FUNÇÕES DE RENDERIZAÇÃO ───────────────────────────────────────────────────
def render_deal_card(j: dict, idx: int, show_btn=True):
    """Card horizontal estilo ITAD."""
    preco  = float(j.get("price") or 0)
    op     = float(j.get("old_price") or 0)
    pct    = j.get("discount_percent") or 0
    store  = j.get("store", "")
    cor    = LOJA_CORES.get(store, "#555")

    badge = ""
    if preco == 0:
        badge = '<span class="badge-free">GRÁTIS</span>'
    elif pct >= 50:
        badge = f'<span class="badge-discount">-{pct}%</span>'

    preco_html = (
        f'<span class="price-current">Gratuito</span>' if preco == 0 else
        f'<span class="price-current">{fmt_preco(preco)}</span>'
    )
    orig_html = (
        f'<span class="price-original">{fmt_preco(op)}</span>' if op > preco > 0 else ""
    )
    store_html = (
        f'<span class="store-tag" style="border-left:3px solid {cor}">{store}</span>'
    )

    capa = j.get("cover_url", "")
    img_html = (f'<img src="{capa}" style="width:110px;border-radius:4px">'
                if capa else
                '<div style="width:110px;height:52px;background:#eee;border-radius:4px"></div>')

    st.markdown(
        f'<div class="deal-card">'
        f'<div class="deal-cover">{img_html}</div>'
        f'<div class="deal-info">'
        f'<div class="deal-title">{j["title"]}</div>'
        f'<div class="deal-platform">{j.get("platform","")}</div>'
        f'<div class="price-row">{preco_html}{orig_html}{badge}{store_html}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    if show_btn:
        gid = j.get("game_id","")
        if st.button("Ver detalhes", key=f"dc_{gid}_{idx}",
                     use_container_width=True):
            st.session_state["jogo_id"] = gid
            st.session_state["goto"]    = "🔍 Buscar"
            st.rerun()


def render_detalhe_jogo(jogo: dict):
    """Página de detalhe estilo ITAD."""
    ofertas = [o for o in ofertas_jogo(jogo["id"]) if o.get("price") is not None]
    ofertas.sort(key=lambda o: float(o["price"]))

    col_capa, col_info = st.columns([1, 2])
    with col_capa:
        if jogo.get("cover_url"):
            st.image(jogo["cover_url"], use_container_width=True)
        st.markdown(f"**{jogo['title']}**")
        st.caption(f"{jogo['platform']} · `{jogo['slug']}`")

    with col_info:
        if not ofertas:
            st.warning("Ainda não há preços. Aguarde o próximo ciclo (6h).")
            return

        menor    = float(ofertas[0]["price"])
        offer_ids = [o["offer_id"] for o in ofertas]
        hist_min  = min_historico(offer_ids)
        is_lowest = hist_min is not None and menor <= hist_min + 0.01

        m1, m2, m3 = st.columns(3)
        m1.metric("💰 Menor preço", fmt_preco(menor))
        if ofertas[0].get("old_price") and float(ofertas[0]["old_price"]) > menor:
            m2.metric("💸 Economia",
                      fmt_preco(float(ofertas[0]["old_price"]) - menor))
        if ofertas[0].get("discount_percent"):
            m3.metric("🏷️ Desconto", f"{ofertas[0]['discount_percent']}%")

        if is_lowest:
            st.success("🏷️ Mínimo histórico — menor preço já registrado!")

        # Tabela de preços estilo ITAD
        st.markdown("#### Ranking de preços")
        linhas_html = ""
        for i, o in enumerate(ofertas):
            preco    = float(o["price"])
            diff     = preco - menor
            diff_pct = (diff / menor * 100) if menor > 0 else 0
            medal    = MEDALHAS.get(i, f"{i+1}º")
            store    = o["store"]
            cor      = LOJA_CORES.get(store, "#555")
            disc_str = f"-{o['discount_percent']}%" if o.get("discount_percent") else "—"

            if preco == 0:
                preco_str = "Gratuito"
            else:
                preco_str = fmt_preco(preco)

            vs_str = (
                "✅ menor" if diff == 0
                else f"+{fmt_preco(diff)} ({diff_pct:.0f}%)"
            )
            linhas_html += (
                f"<tr>"
                f"<td class='rank-medal'>{medal}</td>"
                f"<td><span style='border-left:4px solid {cor};"
                f"padding-left:6px'>{store}</span></td>"
                f"<td><b>{preco_str}</b></td>"
                f"<td>{disc_str}</td>"
                f"<td style='color:#888;font-size:0.8rem'>{vs_str}</td>"
                f"</tr>"
            )

        st.markdown(
            f'<table class="price-table"><thead><tr>'
            f'<th></th><th>Loja</th><th>Preço</th>'
            f'<th>Desconto</th><th>vs. menor</th>'
            f'</tr></thead><tbody>{linhas_html}</tbody></table>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        # Botões de compra
        for o in ofertas:
            preco = float(o["price"])
            store = o["store"]
            cor   = LOJA_CORES.get(store, "#555")
            url   = o.get("product_url", "#")
            label = (f"🆓 Jogar de graça — {store}" if preco == 0
                     else f"🛒 {store} — {fmt_preco(preco)}")
            st.link_button(label, url, use_container_width=True)

        # Histórico
        st.markdown("#### 📈 Histórico de preços")
        mapa_loja = {o["offer_id"]: o["store"] for o in ofertas}
        hist = historico_jogo(list(mapa_loja.keys()))
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
                if hist_min:
                    st.line_chart(pivot)
                    st.caption(f"Mínimo histórico: {fmt_preco(hist_min)}")
                else:
                    st.line_chart(pivot)
        else:
            st.caption("Histórico disponível após mais ciclos de coleta.")

    # Alerta de preço
    st.divider()
    with st.expander("🔔 Criar alerta de preço"):
        c1, c2 = st.columns(2)
        email = c1.text_input("Seu e-mail", key="alerta_email")
        sug   = round(menor * 0.8, 2) if ofertas and menor > 0 else 100.0
        alvo  = c2.number_input("Preço alvo (R$)", min_value=1.0,
                                 value=sug, step=5.0)
        if st.button("🔔 Criar alerta", type="primary"):
            if email and "@" in email:
                registrar_alerta(email, jogo["id"], float(alvo))
                st.success(f"Alerta criado! Você será avisado quando "
                           f"{jogo['title']} ficar abaixo de {fmt_preco(alvo)}.")
            else:
                st.error("E-mail inválido.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINAS
# ══════════════════════════════════════════════════════════════════════════════

# Redireciona click de card
if st.session_state.get("goto"):
    pagina = st.session_state.pop("goto")

# ── DEALS ────────────────────────────────────────────────────────────────────
if pagina == "🏠 Deals":

    # Epic free games banner (topo)
    epic    = epic_free()
    current = epic.get("current", [])
    nexts   = epic.get("next", [])
    if current or nexts:
        st.markdown('<div class="section-header">🎁 Grátis na Epic Games</div>',
                    unsafe_allow_html=True)
        cols = st.columns(min(len(current) + len(nexts), 4))
        for i, g in enumerate(current):
            with cols[i % 4]:
                if g.get("image_url"):
                    st.image(g["image_url"], use_container_width=True)
                end = fmt_data(g["end_date"]) if g.get("end_date") else ""
                st.markdown(
                    f"**{g['title']}**  \n"
                    f"<span class='badge-free'>GRÁTIS</span> "
                    f"<span style='font-size:0.75rem;color:#888'>até {end}</span>",
                    unsafe_allow_html=True,
                )
                st.link_button("Pegar grátis →",
                               "https://store.epicgames.com/pt-BR/free-games",
                               use_container_width=True)
        for i, g in enumerate(nexts):
            with cols[(len(current) + i) % 4]:
                if g.get("image_url"):
                    st.image(g["image_url"], use_container_width=True)
                start = fmt_data(g["start_date"]) if g.get("start_date") else ""
                st.markdown(
                    f"**{g['title']}**  \n"
                    f"<span class='badge-discount'>EM BREVE</span> "
                    f"<span style='font-size:0.75rem;color:#888'>{start}</span>",
                    unsafe_allow_html=True,
                )
        st.divider()

    # Deals principais
    st.markdown('<div class="section-header">🔥 Melhores deals agora</div>',
                unsafe_allow_html=True)
    deals = jogos_com_desconto(
        loja=filtro_loja, plat=filtro_plat,
        min_desc=filtro_desc, limite=40
    )
    if not deals:
        st.info("Nenhum deal encontrado com os filtros selecionados.")
    else:
        for i, j in enumerate(deals):
            render_deal_card(j, i)


# ── BUSCAR / DETALHE ──────────────────────────────────────────────────────────
elif pagina == "🔍 Buscar":

    # Pré-carrega jogo se veio de card
    jogo_pre = None
    if "jogo_id" in st.session_state:
        rows = sb.table("games").select("*")\
                  .eq("id", st.session_state["jogo_id"]).execute().data
        if rows:
            jogo_pre = rows[0]

    col_inp, col_plat, col_btn = st.columns([3, 1, 0.7])
    termo  = col_inp.text_input("🔍 Nome do jogo",
                                placeholder="ex.: Elden Ring, Hades...",
                                key="busca_q")
    plat_b = col_plat.selectbox("Plataforma", PLATAFORMAS, key="busca_plat")
    col_btn.markdown("<br>", unsafe_allow_html=True)
    col_btn.button("Buscar", type="primary", use_container_width=True)

    if termo:
        st.session_state.pop("jogo_id", None)
        jogo_pre = None

    if not termo and jogo_pre is None:
        st.info("Digite o nome de um jogo ou clique em **Ver detalhes** "
                "em qualquer deal.")
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
    render_detalhe_jogo(jogo)


# ── CATÁLOGO ─────────────────────────────────────────────────────────────────
elif pagina == "📚 Catálogo":

    c1, c2, c3 = st.columns([2, 1, 1])
    nome_f = c1.text_input("🔍 Filtrar por nome", key="cat_nome",
                            placeholder="ex.: Elden, Hades...")
    plat_f = c2.selectbox("Plataforma", PLATAFORMAS, key="cat_plat")
    ord_f  = c3.selectbox("Ordenar", ["A-Z","Menor preço","Maior desconto"],
                           key="cat_ord")

    # Busca no catálogo
    q = sb.table("v_game_offers")\
           .select("game_id,title,slug,platform,cover_url,price,discount_percent")\
           .order("title").limit(500)
    if plat_f != "Todas":
        q = q.eq("platform", plat_f)
    rows = q.execute().data

    # Deduplica por menor preço
    visto: dict = {}
    for r in rows:
        gid = r["game_id"]
        p   = float(r.get("price") or 9999)
        if gid not in visto or p < float(visto[gid].get("price") or 9999):
            visto[gid] = r
    jogos_cat = sorted(visto.values(), key=lambda x: x.get("title",""))

    if nome_f:
        jogos_cat = [j for j in jogos_cat
                     if nome_f.lower() in j.get("title","").lower()]
    if ord_f == "Menor preço":
        jogos_cat = sorted(jogos_cat, key=lambda x: float(x.get("price") or 9999))
    elif ord_f == "Maior desconto":
        jogos_cat = sorted(jogos_cat,
                           key=lambda x: x.get("discount_percent") or 0, reverse=True)

    st.caption(f"{len(jogos_cat)} jogos")

    for row_start in range(0, len(jogos_cat), 6):
        cols = st.columns(6)
        for ci, j in enumerate(jogos_cat[row_start:row_start+6]):
            with cols[ci]:
                if j.get("cover_url"):
                    st.image(j["cover_url"], use_container_width=True)
                preco = float(j.get("price") or 0)
                pct   = j.get("discount_percent") or 0
                st.markdown(
                    f'<div style="font-size:0.8rem;font-weight:600;'
                    f'color:#1b2838;line-height:1.2">{j["title"]}</div>'
                    f'<div style="color:#4c9d4c;font-weight:700">'
                    f'{fmt_preco(preco)}'
                    f'{"  " if pct else ""}'
                    f'{"<span style=background:#4c9d4c;color:white;font-size:0.65rem;padding:1px 4px;border-radius:3px>" + str(pct) + "%</span>" if pct else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver", key=f"cat_{j['game_id']}_{row_start+ci}",
                             use_container_width=True):
                    st.session_state["jogo_id"] = j["game_id"]
                    st.session_state["goto"]    = "🔍 Buscar"
                    st.rerun()


# ── STATS ─────────────────────────────────────────────────────────────────────
else:
    st.subheader("📊 Estatísticas do GamePrice Brasil")
    m = metricas()

    c1, c2, c3 = st.columns(3)
    c1.metric("🎮 Jogos", f"{m['total_jogos']:,}")
    c2.metric("💰 Preços coletados", f"{m['total_precos']:,}")
    c3.metric("🏪 Lojas", len(m["lojas"]))

    st.divider()
    c_l, c_r = st.columns(2)

    with c_l:
        st.subheader("Ofertas por loja")
        if m["lojas"]:
            df_l = pd.DataFrame(m["lojas"]).set_index("loja")
            st.bar_chart(df_l["ofertas"])
            st.dataframe(df_l, use_container_width=True)

    with c_r:
        st.subheader("🔥 Maiores descontos ativos")
        top = jogos_com_desconto(limite=10)
        if top:
            df_t = pd.DataFrame([{
                "Jogo":     j["title"],
                "Loja":     j.get("store",""),
                "Preço":    fmt_preco(j.get("price")),
                "Desconto": f"{j.get('discount_percent',0)}%",
            } for j in top])
            st.dataframe(df_t, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("🎁 Epic Games — status atual")
    epic = epic_free()
    c1, c2 = st.columns(2)
    c1.metric("Grátis agora", len(epic.get("current",[])))
    c2.metric("Em breve", len(epic.get("next",[])))
    if epic.get("current"):
        st.caption("Jogos grátis: " +
                   " · ".join(g["title"] for g in epic["current"]))
    if epic.get("updated_at"):
        st.caption(f"Atualizado: {fmt_data(epic['updated_at'])}")
