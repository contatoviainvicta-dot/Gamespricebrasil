"""GamePrice Brasil - layout inspirado no IsThereAnyDeal."""
import pandas as pd
import streamlit as st
from datetime import datetime
from supabase import Client, create_client

st.set_page_config(
    page_title="GamePrice Brasil",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background:#1b2838; border-right:1px solid #2a3f5a; }
[data-testid="stSidebar"] * { color:#c6d4df !important; }
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color:#fff !important; }



.deal-row {
    display:grid; grid-template-columns:96px 1fr auto;
    gap:12px; align-items:center;
    background:#fff; border:1px solid #e0e4e8;
    border-radius:8px; padding:10px 14px; margin-bottom:6px;
}
.deal-row:hover { border-color:#b0bec5; background:#fafbfc; }
.deal-cover { width:96px; height:44px; object-fit:cover; border-radius:4px; }
.deal-cover-ph { width:96px; height:44px; background:#e8edf0; border-radius:4px; }
.deal-title { font-size:.9rem; font-weight:600; color:#1b2838; margin-bottom:2px; }
.deal-meta { font-size:.72rem; color:#888; display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.deal-price { text-align:right; white-space:nowrap; }
.price-now { font-size:1.1rem; font-weight:700; color:#4c9d4c; display:block; }
.price-old { font-size:.78rem; color:#aaa; text-decoration:line-through; display:block; }
.store-pill { font-size:.68rem; font-weight:600; padding:2px 7px; border-radius:3px;
              display:inline-block; background:#f0f2f4; color:#444; border-left:3px solid #aaa; }
.badge { font-size:.68rem; font-weight:700; padding:2px 6px; border-radius:3px; display:inline-block; }
.badge-pct { background:#4c9d4c; color:#fff; }
.badge-free { background:#1b74e8; color:#fff; }
.badge-soon { background:#e6a817; color:#fff; }
.section-hd { font-size:1rem; font-weight:700; color:#1b2838;
              border-left:4px solid #4c9d4c; padding-left:10px; margin:18px 0 10px; }
.rtable { width:100%; border-collapse:collapse; font-size:.85rem; }
.rtable th { background:#f4f6f8; padding:6px 10px; text-align:left;
             font-size:.75rem; color:#666; border-bottom:1px solid #ddd; }
.rtable td { padding:7px 10px; border-bottom:1px solid #f0f0f0; }
.rtable tr:last-child td { border-bottom:none; }
.rtable tr:hover td { background:#f9fbfd; }
</style>
""", unsafe_allow_html=True)

PLATAFORMAS = ["Todas","PC","PS4","PS5","XBOX","SWITCH"]
LOJAS       = ["Todas","Steam","GOG","Humble Store","Epic Games","Nuuvem","Fanatical"]
MEDALHAS    = {0:"🥇",1:"🥈",2:"🥉"}
LOJA_CORES  = {"Steam":"#1b2838","GOG":"#8a2be2","Humble Store":"#cc2200",
               "Epic Games":"#2f4f4f","Nuuvem":"#0066cc","Fanatical":"#ff4500"}

@st.cache_resource
def get_sb() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["anon_key"])
sb = get_sb()

def fmt_preco(v) -> str:
    if v is None: return "—"
    if float(v) == 0: return "Gratuito"
    return f"R$ {float(v):.2f}"

def fmt_data(iso:str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
        return dt.strftime("%d/%m às %H:%Mh")
    except: return iso[:10]

@st.cache_data(ttl=300)
def total_jogos(): return len(sb.table("games").select("id").execute().data)

@st.cache_data(ttl=300)
def jogos_com_desconto(loja="Todas",plat="Todas",min_desc=0,limite=40):
    q = (sb.table("v_game_offers")
         .select("game_id,title,slug,platform,cover_url,store,price,old_price,discount_percent")
         .gt("discount_percent",min_desc).order("discount_percent",desc=True).limit(limite))
    if plat != "Todas": q = q.eq("platform",plat)
    if loja != "Todas": q = q.eq("store",loja)
    return q.execute().data

@st.cache_data(ttl=300)
def buscar_jogos(termo,plat="Todas"):
    q = sb.table("games").select("id,title,slug,platform,cover_url")
    if termo: q = q.ilike("title",f"%{termo}%")
    if plat != "Todas": q = q.eq("platform",plat)
    return q.order("title").limit(100).execute().data

@st.cache_data(ttl=300)
def ofertas_jogo(game_id):
    return sb.table("v_game_offers").select("*").eq("game_id",game_id).execute().data

@st.cache_data(ttl=300)
def historico_jogo(offer_ids):
    if not offer_ids: return []
    return (sb.table("prices").select("offer_id,price,captured_at")
            .in_("offer_id",offer_ids).order("captured_at").execute().data)

@st.cache_data(ttl=300)
def min_historico(offer_ids):
    if not offer_ids: return None
    rows = sb.table("prices").select("price").in_("offer_id",offer_ids).gt("price",0).execute().data
    return min(float(r["price"]) for r in rows) if rows else None

@st.cache_data(ttl=1800)
def epic_free():
    try:
        r = sb.table("epic_free_games").select("current,next,updated_at").eq("id",1).execute().data
        return r[0] if r else {}
    except: return {}

@st.cache_data(ttl=600)
def metricas():
    total_p = len(sb.table("prices").select("id").execute().data)
    lojas_r = sb.table("stores").select("id,name,slug").eq("active",True).execute().data
    cont = []
    for l in lojas_r:
        c = len(sb.table("game_store_offers").select("id")
                .eq("store_id",l["id"]).eq("active",True).execute().data)
        if c > 0: cont.append({"loja":l["name"],"ofertas":c})
    return {"total_jogos":total_jogos(),"total_precos":total_p,
            "lojas":sorted(cont,key=lambda x:x["ofertas"],reverse=True)}

def registrar_alerta(email,game_id,alvo):
    sb.table("alerts").insert({"user_email":email,"game_id":game_id,"target_price":alvo}).execute()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎮 GamePrice Brasil")
    st.divider()
    pagina = st.radio("nav",["🏠 Deals","🔍 Buscar","📚 Catálogo","📊 Stats"],
                      label_visibility="collapsed")
    st.divider()
    st.markdown("**Filtros**")
    filtro_plat = st.selectbox("Plataforma",PLATAFORMAS,key="sb_plat")
    filtro_loja = st.selectbox("Loja",LOJAS,key="sb_loja")
    filtro_desc = st.slider("Desconto mínimo",0,90,0,10,key="sb_desc",format="%d%%")
    st.markdown("**Preço máximo**")
    filtro_preco = st.select_slider("",
        options=["Qualquer","R$ 5","R$ 25","R$ 50","R$ 100","R$ 150"],
        value="Qualquer",key="sb_preco")
    st.divider()
    epic = epic_free()
    current_free = epic.get("current",[])
    if current_free:
        st.markdown("**🎁 Grátis na Epic**")
        for g in current_free:
            st.markdown(f"• {g['title']}")
            if g.get("end_date"): st.caption(f"até {fmt_data(g['end_date'])}")
        st.link_button("Ver na Epic →","https://store.epicgames.com/pt-BR/free-games",
                       use_container_width=True)
    st.divider()
    st.caption(f"📊 {total_jogos()} jogos · Steam · GOG · Humble")

# ── CARD ─────────────────────────────────────────────────────────────────────
def deal_card(j:dict, idx:int):
    preco = float(j.get("price") or 0)
    op    = float(j.get("old_price") or 0)
    pct   = j.get("discount_percent") or 0
    store = j.get("store","")
    cor   = LOJA_CORES.get(store,"#888")
    capa  = j.get("cover_url","")
    img   = (f'<img class="deal-cover" src="{capa}">'
             if capa else '<div class="deal-cover-ph"></div>')
    badge = ""
    if preco == 0: badge = '<span class="badge badge-free">GRÁTIS</span>'
    elif pct > 0:  badge = f'<span class="badge badge-pct">-{pct}%</span>'
    preco_str = "Gratuito" if preco==0 else f"R$ {preco:.2f}"
    old_str   = f'<span class="price-old">R$ {op:.2f}</span>' if op > preco > 0 else ""
    store_tag = f'<span class="store-pill" style="border-left-color:{cor}">{store}</span>'
    plat_tag  = f'<span style="font-size:.68rem;color:#aaa">{j.get("platform","")}</span>'
    st.markdown(f'''<div class="deal-row">
  <div>{img}</div>
  <div>
    <div class="deal-title">{j["title"]}</div>
    <div class="deal-meta">{plat_tag} {store_tag} {badge}</div>
  </div>
  <div class="deal-price">
    <span class="price-now">{preco_str}</span>{old_str}
  </div>
</div>''', unsafe_allow_html=True)
    if st.button("Ver detalhes",key=f"d_{j['game_id']}_{idx}",use_container_width=True):
        st.session_state["jogo_id"] = j["game_id"]
        st.session_state["goto"]    = "🔍 Buscar"
        st.rerun()

# ── DETALHE ───────────────────────────────────────────────────────────────────
def detalhe_jogo(jogo:dict):
    ofertas = [o for o in ofertas_jogo(jogo["id"]) if o.get("price") is not None]
    ofertas.sort(key=lambda o: float(o["price"]))
    col_capa,col_info = st.columns([1,2.5])
    with col_capa:
        if jogo.get("cover_url"): st.image(jogo["cover_url"],use_container_width=True)
        st.markdown(f"**{jogo['title']}**")
        st.caption(f"{jogo['platform']} · `{jogo['slug']}`")
    with col_info:
        if not ofertas:
            st.warning("Ainda não há preços. Aguarde o próximo ciclo (6h)."); return
        menor     = float(ofertas[0]["price"])
        offer_ids = [o["offer_id"] for o in ofertas]
        hist_min  = min_historico(offer_ids)
        is_lowest = hist_min is not None and menor <= hist_min + 0.01
        m1,m2,m3 = st.columns(3)
        m1.metric("💰 Menor preço",fmt_preco(menor))
        if ofertas[0].get("old_price") and float(ofertas[0]["old_price"]) > menor:
            m2.metric("💸 Economia",fmt_preco(float(ofertas[0]["old_price"])-menor))
        if ofertas[0].get("discount_percent"):
            m3.metric("🏷️ Desconto",f"{ofertas[0]['discount_percent']}%")
        if is_lowest: st.success("🏷️ Mínimo histórico — menor preço já registrado!")
        st.markdown("#### Ranking de preços")
        linhas = ""
        for i,o in enumerate(ofertas):
            preco = float(o["price"]); diff = preco-menor
            dpct  = (diff/menor*100) if menor>0 else 0
            store = o["store"]; cor = LOJA_CORES.get(store,"#888")
            disc  = f"-{o['discount_percent']}%" if o.get("discount_percent") else "—"
            vs    = "✅ menor" if diff==0 else f"+{fmt_preco(diff)} ({dpct:.0f}%)"
            linhas += (f"<tr><td>{MEDALHAS.get(i,f'{i+1}º')}</td>"
                       f"<td><span style='border-left:4px solid {cor};padding-left:6px'>{store}</span></td>"
                       f"<td><b>{fmt_preco(preco)}</b></td><td>{disc}</td>"
                       f"<td style='color:#888;font-size:.8rem'>{vs}</td></tr>")
        st.markdown(f'<table class="rtable"><thead><tr><th></th><th>Loja</th>'
                    f'<th>Preço</th><th>Desconto</th><th>vs. menor</th></tr>'
                    f'</thead><tbody>{linhas}</tbody></table>',unsafe_allow_html=True)
        st.markdown("")
        for o in ofertas:
            preco = float(o["price"]); store = o["store"]
            label = f"🆓 Jogar grátis — {store}" if preco==0 else f"🛒 {store} — {fmt_preco(preco)}"
            st.link_button(label,o.get("product_url","#"),use_container_width=True)
        st.markdown("#### 📈 Histórico de preços")
        mapa  = {o["offer_id"]:o["store"] for o in ofertas}
        hist  = historico_jogo(list(mapa.keys()))
        if hist:
            df = pd.DataFrame(hist)
            df["captured_at"] = pd.to_datetime(df["captured_at"])
            df["Loja"]  = df["offer_id"].map(mapa)
            df["price"] = df["price"].astype(float)
            df_g = df[df["price"]>0]
            if not df_g.empty:
                pivot = df_g.pivot_table(index="captured_at",columns="Loja",
                                          values="price",aggfunc="last")
                st.line_chart(pivot)
                if hist_min: st.caption(f"Mínimo histórico: {fmt_preco(hist_min)}")
        else: st.caption("Histórico disponível após mais ciclos de coleta.")
    st.divider()
    with st.expander("🔔 Criar alerta de preço"):
        c1,c2 = st.columns(2)
        email = c1.text_input("Seu e-mail",key="alerta_email")
        sug   = round(menor*0.8,2) if ofertas and menor>0 else 100.0
        alvo  = c2.number_input("Preço alvo (R$)",min_value=1.0,value=sug,step=5.0)
        if st.button("🔔 Criar alerta",type="primary"):
            if email and "@" in email:
                registrar_alerta(email,jogo["id"],float(alvo))
                st.success(f"✅ Alerta criado para {jogo['title']} abaixo de {fmt_preco(alvo)}.")
            else: st.error("E-mail inválido.")

# ── REDIRECIONA ───────────────────────────────────────────────────────────────
if st.session_state.get("goto"):
    pagina = st.session_state.pop("goto")

# ══════════════════════════════════════════════════════════════════════════════
if pagina == "🏠 Deals":
    _L, _C, _R = st.columns([1,6,1])
    with _C:
     epic   = epic_free()
    c_free = epic.get("current",[])
    n_free = epic.get("next",[])
    if c_free or n_free:
        st.markdown('<div class="section-hd">🎁 Grátis na Epic Games esta semana</div>',
                    unsafe_allow_html=True)
        cols = st.columns(min(len(c_free)+len(n_free),4))
        for idx,g in enumerate(c_free):
            with cols[idx%4]:
                if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                end = fmt_data(g["end_date"]) if g.get("end_date") else ""
                st.markdown(f"**{g['title']}**  \n"
                            f'<span class="badge badge-free">GRÁTIS</span> '
                            f'<span style="font-size:.72rem;color:#888">até {end}</span>',
                            unsafe_allow_html=True)
                st.link_button("Pegar grátis →","https://store.epicgames.com/pt-BR/free-games",
                               use_container_width=True)
        for idx,g in enumerate(n_free):
            with cols[(len(c_free)+idx)%4]:
                if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                start = fmt_data(g["start_date"]) if g.get("start_date") else ""
                st.markdown(f"**{g['title']}**  \n"
                            f'<span class="badge badge-soon">EM BREVE</span> '
                            f'<span style="font-size:.72rem;color:#888">{start}</span>',
                            unsafe_allow_html=True)
        st.divider()

    preco_max = None
    if filtro_preco != "Qualquer":
        preco_max = float(filtro_preco.replace("R$ ",""))
    st.markdown('<div class="section-hd">🔥 Melhores deals agora</div>',unsafe_allow_html=True)
    deals = jogos_com_desconto(loja=filtro_loja,plat=filtro_plat,min_desc=filtro_desc,limite=60)
    if preco_max:
        deals = [d for d in deals if float(d.get("price") or 0) <= preco_max]
    if not deals:
        st.info("Nenhum deal encontrado com os filtros selecionados.")
    else:
        st.caption(f"{len(deals)} deals encontrados")
        for i,j in enumerate(deals): deal_card(j,i)

elif pagina == "🔍 Buscar":
    _L, _C, _R = st.columns([1,6,1])
    with _C:
     jogo_pre = None
    if "jogo_id" in st.session_state:
        rows = sb.table("games").select("*").eq("id",st.session_state["jogo_id"]).execute().data
        if rows: jogo_pre = rows[0]
    c1,c2,c3 = st.columns([3,1,.7])
    termo  = c1.text_input("🔍 Nome do jogo",placeholder="ex.: Elden Ring, Hades...",key="q")
    plat_b = c2.selectbox("Plataforma",PLATAFORMAS,key="busca_plat")
    c3.markdown("<br>",unsafe_allow_html=True)
    c3.button("Buscar",type="primary",use_container_width=True)
    if termo:
        st.session_state.pop("jogo_id",None); jogo_pre = None
    if not termo and jogo_pre is None:
        st.info("Digite o nome de um jogo ou clique em **Ver detalhes** em qualquer deal.")
        st.stop()
    if termo:
        jogos = buscar_jogos(termo,plat_b)
        if not jogos: st.warning("Nenhum jogo encontrado."); st.stop()
        titulos = {f"{j['title']}  ({j['platform']})":j for j in jogos}
        jogo = jogos[0] if len(jogos)==1 else titulos[st.selectbox("Selecione",list(titulos.keys()))]
    else:
        jogo = jogo_pre
    st.divider()
    detalhe_jogo(jogo)

elif pagina == "📚 Catálogo":
    _L, _C, _R = st.columns([1,6,1])
    with _C:
     c1,c2,c3 = st.columns([2,1,1])
    nome_f = c1.text_input("🔍 Nome",key="cat_nome",placeholder="ex.: Elden, Hades...")
    plat_f = c2.selectbox("Plataforma",PLATAFORMAS,key="cat_plat")
    ord_f  = c3.selectbox("Ordenar",["A-Z","Menor preço","Maior desconto"],key="cat_ord")
    q = sb.table("v_game_offers")\
           .select("game_id,title,slug,platform,cover_url,price,discount_percent")\
           .order("title").limit(500)
    if plat_f != "Todas": q = q.eq("platform",plat_f)
    rows = q.execute().data
    visto:dict = {}
    for r in rows:
        gid = r["game_id"]; p = float(r.get("price") or 9999)
        if gid not in visto or p < float(visto[gid].get("price") or 9999): visto[gid] = r
    jogos_cat = sorted(visto.values(),key=lambda x:x.get("title",""))
    if nome_f: jogos_cat = [j for j in jogos_cat if nome_f.lower() in j.get("title","").lower()]
    if ord_f=="Menor preço": jogos_cat = sorted(jogos_cat,key=lambda x:float(x.get("price") or 9999))
    elif ord_f=="Maior desconto": jogos_cat = sorted(jogos_cat,key=lambda x:x.get("discount_percent") or 0,reverse=True)
    st.caption(f"{len(jogos_cat)} jogos")
    for rs in range(0,len(jogos_cat),6):
        cols = st.columns(6)
        for ci,j in enumerate(jogos_cat[rs:rs+6]):
            with cols[ci]:
                if j.get("cover_url"): st.image(j["cover_url"],use_container_width=True)
                preco = float(j.get("price") or 0); pct = j.get("discount_percent") or 0
                badge = f'<span class="badge badge-pct">-{pct}%</span>' if pct else ""
                st.markdown(
                    f'<div style="font-size:.8rem;font-weight:600;color:#1b2838;line-height:1.2">{j["title"]}</div>'
                    f'<div style="color:#4c9d4c;font-weight:700;font-size:.85rem">{fmt_preco(preco)} {badge}</div>',
                    unsafe_allow_html=True)
                if st.button("Ver",key=f"cat_{j['game_id']}_{rs+ci}",use_container_width=True):
                    st.session_state["jogo_id"] = j["game_id"]
                    st.session_state["goto"]    = "🔍 Buscar"
                    st.rerun()

else:
    _L, _C, _R = st.columns([1,6,1])
    with _C:
     st.subheader("📊 Estatísticas do GamePrice Brasil")
    m = metricas()
    c1,c2,c3 = st.columns(3)
    c1.metric("🎮 Jogos",f"{m['total_jogos']:,}")
    c2.metric("💰 Preços coletados",f"{m['total_precos']:,}")
    c3.metric("🏪 Lojas",len(m["lojas"]))
    st.divider()
    c_l,c_r = st.columns(2)
    with c_l:
        st.subheader("Ofertas por loja")
        if m["lojas"]:
            df_l = pd.DataFrame(m["lojas"]).set_index("loja")
            st.bar_chart(df_l["ofertas"])
            st.dataframe(df_l,use_container_width=True)
    with c_r:
        st.subheader("🔥 Maiores descontos ativos")
        top = jogos_com_desconto(limite=10)
        if top:
            st.dataframe(pd.DataFrame([{
                "Jogo":j["title"],"Loja":j.get("store",""),
                "Preço":fmt_preco(j.get("price")),"Desconto":f"{j.get('discount_percent',0)}%"
            } for j in top]),hide_index=True,use_container_width=True)
    st.divider()
    epic = epic_free()
    c1,c2 = st.columns(2)
    c1.metric("Grátis agora",len(epic.get("current",[])))
    c2.metric("Em breve",len(epic.get("next",[])))
    if epic.get("current"): st.caption("Grátis: "+" · ".join(g["title"] for g in epic["current"]))
    if epic.get("updated_at"): st.caption(f"Atualizado: {fmt_data(epic['updated_at'])}")
