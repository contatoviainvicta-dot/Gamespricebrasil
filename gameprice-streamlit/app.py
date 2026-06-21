"""GamePrice Brasil - comparador de preços estilo ITAD."""
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
/* Sidebar */
[data-testid="stSidebar"] { background:#1b2838 !important; }
[data-testid="stSidebar"] * { color:#c6d4df !important; }
[data-testid="stSidebar"] h1,h2,h3 { color:#fff !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label { color:#8fa3b1 !important; font-size:.8rem !important; }

/* Card de deal */
.deal {
    display:flex; gap:12px; align-items:center;
    background:#fff; border:1px solid #dde3e8;
    border-radius:6px; padding:10px 14px;
    margin-bottom:5px; transition:border .15s;
}
.deal:hover { border-color:#a0b4c0; }
.deal img { width:80px; height:45px; object-fit:cover; border-radius:4px; flex-shrink:0; }
.deal-body { flex:1; min-width:0; }
.deal-name { font-weight:600; font-size:.88rem; color:#1b2838;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.deal-sub { font-size:.72rem; color:#90a4b0; margin-top:2px;
            display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.deal-right { text-align:right; flex-shrink:0; }
.deal-price { font-size:1rem; font-weight:700; color:#3a8a3a; }
.deal-orig  { font-size:.75rem; color:#b0bec5; text-decoration:line-through; }

/* Badges */
.b { display:inline-block; font-size:.65rem; font-weight:700;
     padding:1px 5px; border-radius:3px; }
.b-green { background:#3a8a3a; color:#fff; }
.b-blue  { background:#1565c0; color:#fff; }
.b-amber { background:#e65100; color:#fff; }

/* Loja pill */
.loja { display:inline-block; font-size:.7rem; padding:1px 6px;
        border-radius:3px; background:#f0f4f7; color:#546e7a;
        border-left:3px solid #90a4b0; }

/* Section header */
.sh { font-size:.95rem; font-weight:700; color:#1b2838;
      border-left:3px solid #3a8a3a; padding-left:8px; margin:12px 0 8px; }

/* Ranking table */
.rt { width:100%; border-collapse:collapse; font-size:.83rem; margin-top:6px; }
.rt th { background:#f5f7f9; padding:5px 10px; text-align:left;
         color:#78909c; font-size:.73rem; border-bottom:1px solid #e0e7ec; }
.rt td { padding:6px 10px; border-bottom:1px solid #f0f4f7; }
.rt tr:hover td { background:#f9fbfd; }

/* Epic banner */
.epic-card { background:#16202d; border-radius:8px; padding:0;
             overflow:hidden; margin-bottom:4px; }
.epic-card img { width:100%; height:120px; object-fit:cover; display:block; }
.epic-info { padding:8px 10px; }
.epic-title { font-size:.82rem; font-weight:600; color:#e8eef2; margin-bottom:4px; }
</style>
""", unsafe_allow_html=True)

PLAT   = ["Todas","PC","PS4","PS5","XBOX","SWITCH"]
LOJAS  = ["Todas","Steam","GOG","Humble Store","Epic Games","Nuuvem","Fanatical"]
MED    = {0:"🥇",1:"🥈",2:"🥉"}
CORES  = {"Steam":"#1b2838","GOG":"#8a2be2","Humble Store":"#c62828",
          "Epic Games":"#37474f","Nuuvem":"#1565c0","Fanatical":"#bf360c"}

@st.cache_resource
def sb():
    c = st.secrets["supabase"]
    return create_client(c["url"],c["anon_key"])
SB = sb()

def R(v):
    if v is None: return "—"
    return "Gratuito" if float(v)==0 else f"R$ {float(v):.2f}"

def DT(iso):
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).strftime("%d/%m %H:%Mh")
    except: return iso[:10]

@st.cache_data(ttl=300)
def n_jogos(): return len(SB.table("games").select("id").execute().data)

@st.cache_data(ttl=300)
def deals(loja="Todas",plat="Todas",disc=0,lim=50):
    q = (SB.table("v_game_offers")
         .select("game_id,title,platform,cover_url,store,price,old_price,discount_percent")
         .gt("discount_percent",disc).order("discount_percent",desc=True).limit(lim))
    if plat!="Todas": q=q.eq("platform",plat)
    if loja!="Todas": q=q.eq("store",loja)
    return q.execute().data

@st.cache_data(ttl=300)
def buscar(t,p="Todas"):
    q=SB.table("games").select("id,title,slug,platform,cover_url")
    if t: q=q.ilike("title",f"%{t}%")
    if p!="Todas": q=q.eq("platform",p)
    return q.order("title").limit(100).execute().data

@st.cache_data(ttl=300)
def ofertas(gid):
    return SB.table("v_game_offers").select("*").eq("game_id",gid).execute().data

@st.cache_data(ttl=300)
def hist(oids):
    if not oids: return []
    return SB.table("prices").select("offer_id,price,captured_at").in_("offer_id",oids).order("captured_at").execute().data

@st.cache_data(ttl=300)
def hmin(oids):
    if not oids: return None
    r=SB.table("prices").select("price").in_("offer_id",oids).gt("price",0).execute().data
    return min(float(x["price"]) for x in r) if r else None

@st.cache_data(ttl=1800)
def epic():
    try:
        r=SB.table("epic_free_games").select("current,next,updated_at").eq("id",1).execute().data
        return r[0] if r else {}
    except: return {}

@st.cache_data(ttl=600)
def stats():
    tp=len(SB.table("prices").select("id").execute().data)
    ls=SB.table("stores").select("id,name").eq("active",True).execute().data
    cont=[]
    for l in ls:
        c=len(SB.table("game_store_offers").select("id").eq("store_id",l["id"]).eq("active",True).execute().data)
        if c>0: cont.append({"loja":l["name"],"ofertas":c})
    return {"jogos":n_jogos(),"precos":tp,"lojas":sorted(cont,key=lambda x:x["ofertas"],reverse=True)}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎮 GamePrice Brasil")
    st.divider()
    pag = st.radio("p",["🏠 Deals","🔍 Buscar","📚 Catálogo","📊 Stats"],label_visibility="collapsed")
    st.divider()
    st.markdown("**Filtros**")
    fp = st.selectbox("Plataforma",PLAT,key="fp")
    fl = st.selectbox("Loja",LOJAS,key="fl")
    fd = st.slider("Desconto mín.",0,90,0,10,key="fd",format="%d%%")
    fm = st.select_slider("Preço máx.",["Qualquer","R$ 5","R$ 25","R$ 50","R$ 100","R$ 150"],value="Qualquer",key="fm")
    st.divider()
    ep=epic(); cf=ep.get("current",[])
    if cf:
        st.markdown("**🎁 Grátis na Epic**")
        for g in cf:
            st.markdown(f"• **{g['title']}**")
            if g.get("end_date"): st.caption(f"até {DT(g['end_date'])}")
        st.link_button("Ver na Epic →","https://store.epicgames.com/pt-BR/free-games",use_container_width=True)
    st.divider()
    st.caption(f"📊 {n_jogos()} jogos · Steam · GOG · Humble")

# ── COMPONENTES ───────────────────────────────────────────────────────────────
def card(j,i):
    pr=float(j.get("price") or 0); op=float(j.get("old_price") or 0)
    pc=j.get("discount_percent") or 0; st_=j.get("store",""); cor=CORES.get(st_,"#90a4b0")
    img=j.get("cover_url","")
    img_h=f'<img src="{img}">' if img else '<div style="width:80px;height:45px;background:#e8edf0;border-radius:4px;flex-shrink:0"></div>'
    bdg=('<span class="b b-blue">GRÁTIS</span>' if pr==0
         else f'<span class="b b-green">-{pc}%</span>' if pc>0 else "")
    pr_h="Gratuito" if pr==0 else f"R$ {pr:.2f}"
    op_h=f'<div class="deal-orig">R$ {op:.2f}</div>' if op>pr>0 else ""
    lo_h=f'<span class="loja" style="border-left-color:{cor}">{st_}</span>'
    pl_h=f'<span style="color:#b0bec5;font-size:.7rem">{j.get("platform","")}</span>'
    st.markdown(f'''<div class="deal">
{img_h}
<div class="deal-body">
  <div class="deal-name">{j["title"]}</div>
  <div class="deal-sub">{pl_h}{lo_h}{bdg}</div>
</div>
<div class="deal-right">
  <div class="deal-price">{pr_h}</div>{op_h}
</div>
</div>''',unsafe_allow_html=True)
    if st.button("Ver detalhes",key=f"c{j['game_id']}{i}",use_container_width=True):
        st.session_state.update({"jogo_id":j["game_id"],"goto":"🔍 Buscar"}); st.rerun()

def detalhe(jg):
    ofs=[o for o in ofertas(jg["id"]) if o.get("price") is not None]
    ofs.sort(key=lambda o:float(o["price"]))
    ca,ci=st.columns([1,2.5])
    with ca:
        if jg.get("cover_url"): st.image(jg["cover_url"],use_container_width=True)
        st.markdown(f"**{jg['title']}**"); st.caption(f"{jg['platform']}")
    with ci:
        if not ofs: st.warning("Sem preços ainda."); return
        mn=float(ofs[0]["price"]); oids=[o["offer_id"] for o in ofs]
        hm=hmin(oids); low=hm is not None and mn<=hm+.01
        m1,m2,m3=st.columns(3)
        m1.metric("💰 Menor",R(mn))
        if ofs[0].get("old_price") and float(ofs[0]["old_price"])>mn:
            m2.metric("💸 Economia",R(float(ofs[0]["old_price"])-mn))
        if ofs[0].get("discount_percent"): m3.metric("🏷️",f"{ofs[0]['discount_percent']}%")
        if low: st.success("🏷️ Mínimo histórico!")
        rows=""
        for i,o in enumerate(ofs):
            pr=float(o["price"]); df=pr-mn; dp=(df/mn*100) if mn>0 else 0
            cor=CORES.get(o["store"],"#90a4b0")
            disc=f"-{o['discount_percent']}%" if o.get("discount_percent") else "—"
            vs="✅ menor" if df==0 else f"+{R(df)} ({dp:.0f}%)"
            rows+=(f"<tr><td>{MED.get(i,f'{i+1}º')}</td>"
                   f"<td><span style='border-left:3px solid {cor};padding-left:6px'>{o['store']}</span></td>"
                   f"<td><b>{R(pr)}</b></td><td>{disc}</td>"
                   f"<td style='color:#90a4b0;font-size:.8rem'>{vs}</td></tr>")
        st.markdown(f'<table class="rt"><thead><tr><th></th><th>Loja</th><th>Preço</th><th>Desc.</th><th>vs menor</th></tr></thead><tbody>{rows}</tbody></table>',unsafe_allow_html=True)
        st.markdown("")
        for o in ofs:
            pr=float(o["price"]); lb=f"🆓 {o['store']} — Grátis" if pr==0 else f"🛒 {o['store']} — {R(pr)}"
            st.link_button(lb,o.get("product_url","#"),use_container_width=True)
        st.markdown("#### 📈 Histórico")
        mp={o["offer_id"]:o["store"] for o in ofs}
        h=hist(list(mp.keys()))
        if h:
            df=pd.DataFrame(h); df["captured_at"]=pd.to_datetime(df["captured_at"])
            df["Loja"]=df["offer_id"].map(mp); df["price"]=df["price"].astype(float)
            dg=df[df["price"]>0]
            if not dg.empty:
                pv=dg.pivot_table(index="captured_at",columns="Loja",values="price",aggfunc="last")
                st.line_chart(pv)
                if hm: st.caption(f"Mínimo histórico: {R(hm)}")
        else: st.caption("Histórico disponível após mais coletas.")
    st.divider()
    with st.expander("🔔 Criar alerta"):
        c1,c2=st.columns(2)
        em=c1.text_input("E-mail",key="ae")
        sg=round(mn*.8,2) if ofs and mn>0 else 100.
        al=c2.number_input("Preço alvo (R$)",min_value=1.,value=sg,step=5.)
        if st.button("🔔 Criar",type="primary"):
            if em and "@" in em:
                SB.table("alerts").insert({"user_email":em,"game_id":jg["id"],"target_price":float(al)}).execute()
                st.success(f"Alerta criado! Aviso quando {jg['title']} < {R(al)}")
            else: st.error("E-mail inválido.")

# ── NAVEGAÇÃO ─────────────────────────────────────────────────────────────────
if st.session_state.get("goto"):
    pag = st.session_state.pop("goto")

# Colunas: margem | conteúdo | margem
mg = [0.5, 7, 0.5]

# ══════════════════════════════════════════════════════════════════════════════
if pag == "🏠 Deals":
    _,C,_ = st.columns(mg)
    with C:
        ep=epic(); cf=ep.get("current",[]); nf=ep.get("next",[])
        if cf or nf:
            st.markdown('<div class="sh">🎁 Grátis na Epic esta semana</div>',unsafe_allow_html=True)
            cols=st.columns(min(len(cf)+len(nf),4))
            for i,g in enumerate(cf):
                with cols[i%4]:
                    if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                    end=DT(g["end_date"]) if g.get("end_date") else ""
                    st.markdown(f"**{g['title']}**")
                    st.markdown(f'<span class="b b-blue">GRÁTIS</span> <span style="font-size:.7rem;color:#888">até {end}</span>',unsafe_allow_html=True)
                    st.link_button("Pegar grátis →","https://store.epicgames.com/pt-BR/free-games",use_container_width=True)
            for i,g in enumerate(nf):
                with cols[(len(cf)+i)%4]:
                    if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                    st.markdown(f"**{g['title']}**")
                    st.markdown(f'<span class="b b-amber">EM BREVE</span>',unsafe_allow_html=True)
            st.divider()

        pm=None
        if fm!="Qualquer": pm=float(fm.replace("R$ ",""))
        st.markdown('<div class="sh">🔥 Melhores deals agora</div>',unsafe_allow_html=True)
        ds=deals(fl,fp,fd,60)
        if pm: ds=[d for d in ds if float(d.get("price") or 0)<=pm]
        if not ds: st.info("Nenhum deal com esses filtros.")
        else:
            st.caption(f"{len(ds)} deals")
            for i,j in enumerate(ds): card(j,i)

elif pag == "🔍 Buscar":
    _,C,_ = st.columns(mg)
    with C:
        jp=None
        if "jogo_id" in st.session_state:
            r=SB.table("games").select("*").eq("id",st.session_state["jogo_id"]).execute().data
            if r: jp=r[0]
        c1,c2,c3=st.columns([3,1,.7])
        t=c1.text_input("🔍 Nome do jogo",placeholder="ex.: Elden Ring, Witcher...",key="q")
        pb=c2.selectbox("Plataforma",PLAT,key="pb")
        c3.markdown("<br>",unsafe_allow_html=True); c3.button("Buscar",type="primary",use_container_width=True)
        if t: st.session_state.pop("jogo_id",None); jp=None
        if not t and jp is None:
            st.info("Digite o nome de um jogo ou clique em **Ver detalhes**."); st.stop()
        if t:
            js=buscar(t,pb)
            if not js: st.warning("Nenhum jogo."); st.stop()
            tit={f"{j['title']} ({j['platform']})":j for j in js}
            jg=js[0] if len(js)==1 else tit[st.selectbox("Selecione",list(tit.keys()))]
        else: jg=jp
        st.divider(); detalhe(jg)

elif pag == "📚 Catálogo":
    _,C,_ = st.columns(mg)
    with C:
        c1,c2,c3=st.columns([2,1,1])
        nm=c1.text_input("🔍 Nome",key="cn",placeholder="ex.: Hades, Elden...")
        pt=c2.selectbox("Plataforma",PLAT,key="cp")
        od=c3.selectbox("Ordenar",["A-Z","Menor preço","Maior desconto"],key="co")
        q=SB.table("v_game_offers").select("game_id,title,platform,cover_url,price,discount_percent").order("title").limit(500)
        if pt!="Todas": q=q.eq("platform",pt)
        rows=q.execute().data
        vis={}
        for r in rows:
            g=r["game_id"]; p=float(r.get("price") or 9999)
            if g not in vis or p<float(vis[g].get("price") or 9999): vis[g]=r
        jc=sorted(vis.values(),key=lambda x:x.get("title",""))
        if nm: jc=[j for j in jc if nm.lower() in j.get("title","").lower()]
        if od=="Menor preço": jc=sorted(jc,key=lambda x:float(x.get("price") or 9999))
        elif od=="Maior desconto": jc=sorted(jc,key=lambda x:x.get("discount_percent") or 0,reverse=True)
        st.caption(f"{len(jc)} jogos")
        for rs in range(0,len(jc),5):
            cols=st.columns(5)
            for ci,j in enumerate(jc[rs:rs+5]):
                with cols[ci]:
                    if j.get("cover_url"): st.image(j["cover_url"],use_container_width=True)
                    pc=j.get("discount_percent") or 0
                    bx=f'<span class="b b-green">-{pc}%</span>' if pc else ""
                    st.markdown(f'<div style="font-size:.78rem;font-weight:600;color:#1b2838;line-height:1.2;margin-top:3px">{j["title"]}</div>'
                                f'<div style="color:#3a8a3a;font-weight:700;font-size:.82rem">{R(j.get("price"))} {bx}</div>',unsafe_allow_html=True)
                    if st.button("Ver",key=f"ct{j['game_id']}{rs+ci}",use_container_width=True):
                        st.session_state.update({"jogo_id":j["game_id"],"goto":"🔍 Buscar"}); st.rerun()

else:
    _,C,_ = st.columns(mg)
    with C:
        st.subheader("📊 Estatísticas")
        s=stats()
        c1,c2,c3=st.columns(3)
        c1.metric("🎮 Jogos",f"{s['jogos']:,}")
        c2.metric("💰 Preços",f"{s['precos']:,}")
        c3.metric("🏪 Lojas",len(s["lojas"]))
        st.divider()
        cL,cR=st.columns(2)
        with cL:
            st.markdown("**Ofertas por loja**")
            if s["lojas"]:
                df=pd.DataFrame(s["lojas"]).set_index("loja")
                st.bar_chart(df["ofertas"])
        with cR:
            st.markdown("**🔥 Top descontos**")
            top=deals(lim=10)
            if top:
                st.dataframe(pd.DataFrame([{"Jogo":j["title"],"Loja":j.get("store",""),
                    "Preço":R(j.get("price")),"Desc":f"{j.get('discount_percent',0)}%"}
                    for j in top]),hide_index=True,use_container_width=True)
        ep=epic(); c1,c2=st.columns(2)
        c1.metric("Grátis Epic",len(ep.get("current",[])))
        c2.metric("Em breve",len(ep.get("next",[])))
