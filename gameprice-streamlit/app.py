"""GamePrice Brasil — comparador de preços estilo ITAD."""
import pandas as pd
import streamlit as st
from datetime import datetime
from supabase import Client, create_client

st.set_page_config(page_title="GamePrice Brasil", page_icon="🎮",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
[data-testid="stSidebar"] { background:#1b2838 !important; }
[data-testid="stSidebar"] * { color:#c6d4df !important; }
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2 { color:#fff !important; }
.deal { display:flex;gap:12px;align-items:center;background:#fff;
        border:1px solid #dde3e8;border-radius:6px;padding:8px 12px;margin-bottom:4px; }
.deal:hover { border-color:#a0b4c0; }
.deal img { width:100px;height:56px;object-fit:cover;border-radius:4px;flex-shrink:0; }
.dn { font-weight:600;font-size:.88rem;color:#1b2838;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.ds { font-size:.72rem;color:#90a4b0;margin-top:3px;display:flex;gap:6px;align-items:center; }
.dr { text-align:right;flex-shrink:0; }
.rt { width:100%;border-collapse:collapse;font-size:.83rem; }
.rt th { background:#f5f7f9;padding:5px 10px;text-align:left;
         color:#78909c;font-size:.73rem;border-bottom:1px solid #e0e7ec; }
.rt td { padding:6px 10px;border-bottom:1px solid #f0f4f7; }
.sh { font-size:.95rem;font-weight:700;color:#1b2838;
      border-left:3px solid #3a8a3a;padding-left:8px;margin:12px 0 8px; }
</style>""", unsafe_allow_html=True)

PLAT  = ["Todas","PC","PS4","PS5","XBOX","SWITCH"]
LOJAS = ["Todas","Steam","GOG","Humble Store","Epic Games","Nuuvem","Fanatical"]
MED   = {0:"🥇",1:"🥈",2:"🥉"}
CORES = {"Steam":"#1b2838","GOG":"#8a2be2","Humble Store":"#c62828",
         "Epic Games":"#37474f","Nuuvem":"#1565c0","Fanatical":"#bf360c"}
LOJA_DOTS = {"Steam":"#4caf50","GOG":"#ff9800","Humble Store":"#f44336",
             "Epic Games":"#9c27b0","Nuuvem":"#2196f3","Fanatical":"#ff5722"}

@st.cache_resource
def SB():
    c = st.secrets["supabase"]
    return create_client(c["url"], c["anon_key"])
DB = SB()

def R(v):
    if v is None: return "—"
    return "Gratuito" if float(v)==0 else f"R$ {float(v):.2f}"

def DT(iso):
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).strftime("%d/%m %H:%Mh")
    except: return iso[:10]

@st.cache_data(ttl=300)
def n_jogos(): return len(DB.table("games").select("id").execute().data)

@st.cache_data(ttl=300)
def get_deals(loja="Todas",plat="Todas",disc=0,lim=50):
    q = (DB.table("v_game_offers")
         .select("game_id,title,platform,cover_url,store,price,old_price,discount_percent")
         .gt("discount_percent",disc).order("discount_percent",desc=True).limit(lim))
    if plat!="Todas": q=q.eq("platform",plat)
    if loja!="Todas": q=q.eq("store",loja)
    return q.execute().data

@st.cache_data(ttl=300)
def buscar(t,p="Todas"):
    q=DB.table("games").select("id,title,slug,platform,cover_url")
    if t: q=q.ilike("title",f"%{t}%")
    if p!="Todas": q=q.eq("platform",p)
    return q.order("title").limit(100).execute().data

@st.cache_data(ttl=300)
def get_ofertas(gid):
    return DB.table("v_game_offers").select("*").eq("game_id",gid).execute().data

@st.cache_data(ttl=300)
def get_hist(oids):
    if not oids: return []
    return (DB.table("prices").select("offer_id,price,captured_at")
            .in_("offer_id",oids).order("captured_at").execute().data)

@st.cache_data(ttl=300)
def get_hmin(oids):
    if not oids: return None
    r=DB.table("prices").select("price").in_("offer_id",oids).gt("price",0).execute().data
    return min(float(x["price"]) for x in r) if r else None

@st.cache_data(ttl=1800)
def get_epic():
    try:
        r=DB.table("epic_free_games").select("current,next,updated_at").eq("id",1).execute().data
        return r[0] if r else {}
    except: return {}

@st.cache_data(ttl=600)
def get_stats():
    tp=len(DB.table("prices").select("id").execute().data)
    ls=DB.table("stores").select("id,name").eq("active",True).execute().data
    cont=[]
    for l in ls:
        c=len(DB.table("game_store_offers").select("id").eq("store_id",l["id"]).eq("active",True).execute().data)
        if c>0: cont.append({"loja":l["name"],"ofertas":c})
    return {"jogos":n_jogos(),"precos":tp,"lojas":sorted(cont,key=lambda x:x["ofertas"],reverse=True)}

@st.cache_data(ttl=600)
def get_price_history(game_id):
    try:
        oids=[o["offer_id"] for o in DB.table("v_game_offers").select("offer_id").eq("game_id",game_id).execute().data]
        if not oids: return []
        return DB.table("prices").select("price,captured_at").in_("offer_id",oids).gt("price",0).order("captured_at").execute().data
    except: return []

@st.cache_data(ttl=3600)
def get_desc(game_id):
    import httpx
    try:
        store=DB.table("stores").select("id").eq("slug","steam").execute().data
        if not store: return {}
        offer=DB.table("game_store_offers").select("external_id").eq("game_id",game_id).eq("store_id",store[0]["id"]).execute().data
        if not offer: return {}
        appid=offer[0]["external_id"]
        r=httpx.get("https://store.steampowered.com/api/appdetails",
            params={"appids":appid,"cc":"br","l":"portuguese",
                    "filters":"basic,short_description,genres,release_date,metacritic,recommendations"},
            timeout=10,headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        data=r.json().get(str(appid),{})
        if not data.get("success"): return {}
        d=data.get("data",{})
        rec=d.get("recommendations",{})
        return {
            "short_description":d.get("short_description",""),
            "header_image":d.get("header_image",""),
            "genres":[g["description"] for g in d.get("genres",[])],
            "release_date":d.get("release_date",{}).get("date",""),
            "metacritic":d.get("metacritic",{}).get("score") if d.get("metacritic") else None,
            "steam_reviews":rec.get("total",0) if isinstance(rec,dict) else 0,
        }
    except: return {}

def render_price_bars(hist_data, preco_atual):
    df=pd.DataFrame(hist_data)
    df["captured_at"]=pd.to_datetime(df["captured_at"],utc=True)
    df["price"]=df["price"].astype(float)
    df["dia"]=df["captured_at"].dt.date
    df_day=df.groupby("dia")["price"].min().reset_index().tail(90)
    if df_day.empty or len(df_day)<2:
        st.caption("Poucos dados ainda — gráfico disponível em breve.")
        return
    pmax=df_day["price"].max(); pmin=df_day["price"].min()
    n=len(df_day); bw=max(2,(600-n)//n); h=60; tw=n*(bw+1)
    bars=""
    for idx,(_,row) in enumerate(df_day.iterrows()):
        p=row["price"]; bh=max(3,int(h*0.15+h*0.85*(1-(p-pmin)/(pmax-pmin+.01))))
        by=h-bh; x=idx*(bw+1)
        c="#43a047" if p<=pmin*1.05 else "#fb8c00" if p<=pmin*1.5 else "#e53935"
        bars+="<rect x='"+str(x)+"' y='"+str(by)+"' width='"+str(bw)+"' height='"+str(bh)+"' fill='"+c+"' rx='1'/>"
    d0=str(df_day["dia"].iloc[0]); d1=str(df_day["dia"].iloc[-1])
    svg=("<svg viewBox='0 0 "+str(tw)+" "+str(h+20)+"' xmlns='http://www.w3.org/2000/svg' style='width:100%;height:85px'>"
         "<rect width='"+str(tw)+"' height='"+str(h)+"' fill='#f0f4f7' rx='4'/>"+bars
         +"<text x='2' y='"+str(h+13)+"' font-size='8' fill='#90a4b0'>"+d0+"</text>"
         "<text x='"+str(tw-2)+"' y='"+str(h+13)+"' font-size='8' fill='#90a4b0' text-anchor='end'>"+d1+"</text>"
         "<text x='"+str(tw//2)+"' y='"+str(h+13)+"' font-size='8' fill='#37474f' text-anchor='middle'>"
         "Min: R$"+str(round(pmin,2))+" | Max: R$"+str(round(pmax,2))+"</text></svg>")
    st.markdown(svg,unsafe_allow_html=True)
    st.markdown("<div style='display:flex;gap:12px;font-size:.7rem;color:#607d8b'>"
                "<span><span style='color:#43a047'>■</span> Mínimo</span>"
                "<span><span style='color:#fb8c00'>■</span> Médio</span>"
                "<span><span style='color:#e53935'>■</span> Alto</span></div>",
                unsafe_allow_html=True)

def painel_expandido(j, idx=0):
    """Painel expansível com descrição, gráfico e preços por loja."""
    desc=get_desc(j["game_id"])
    hist=get_price_history(j["game_id"])
    _all2 = [o for o in get_ofertas(j["game_id"]) if o.get("price") is not None]
    _seen2 = {}
    for o in sorted(_all2, key=lambda o: float(o["price"])):
        lj = o.get("store","")
        if lj not in _seen2:
            _seen2[lj] = o
    ofs = sorted(_seen2.values(), key=lambda o: float(o["price"]))

    pa,pb=st.columns([1,2])
    with pa:
        if desc.get("header_image"): st.image(desc["header_image"],use_container_width=True)
        if desc.get("genres"): st.caption("🏷 "+" · ".join(desc["genres"]))
        if desc.get("release_date"): st.caption("📅 "+desc["release_date"])
    with pb:
        st.markdown("**"+j["title"]+"**")
        if desc.get("short_description"): st.write(desc["short_description"])
        mc=desc.get("metacritic"); sr=desc.get("steam_reviews",0)
        if mc:
            cm="#43a047" if int(mc)>=75 else "#fb8c00" if int(mc)>=50 else "#e53935"
            st.markdown("<div style='display:flex;align-items:center;gap:8px;margin:4px 0'>"
                        "<div style='flex:1;background:#e0e0e0;border-radius:3px;height:6px'>"
                        "<div style='width:"+str(mc)+"%;background:"+cm+";height:6px;border-radius:3px'></div>"
                        "</div><span style='font-size:.75rem;color:#546e7a'>Metacritic "+str(mc)+"</span></div>",
                        unsafe_allow_html=True)
        if sr>0: st.caption("💬 "+"{:,}".format(sr)+" avaliações na Steam")

    if hist:
        st.markdown("**📊 Histórico de preços (últimos 90 dias)**")
        render_price_bars(hist,j.get("price"))

    if ofs:
        st.markdown("**🏪 Preços por loja**")
        for o in ofs:
            pr=float(o["price"]); op2=float(o.get("old_price") or pr)
            pc2=o.get("discount_percent") or 0; st_=o["store"]
            cor=CORES.get(st_,"#90a4b0")
            prc="#ef5350" if pc2>=50 else "#fb8c00" if pc2>0 else "#37474f"
            disc=("-"+str(pc2)+"% ") if pc2>0 else ""
            low=("store low: R$ "+str(round(min(pr,op2),2))) if op2>pr else ""
            st.markdown("<div style='display:flex;align-items:center;justify-content:space-between;"
                        "padding:5px 0;border-bottom:1px solid #eee;font-size:.82rem'>"
                        "<span><span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
                        "background:"+cor+";margin-right:5px;vertical-align:middle'></span><b>"+st_+"</b></span>"
                        "<span style='color:#90a4b0;font-size:.72rem'>"+low+"</span>"
                        "<span style='color:"+prc+";font-weight:700'>"+disc+"R$ "+str(round(pr,2))+"</span></div>",
                        unsafe_allow_html=True)
        st.markdown("")
        if st.button("🔗 Ver página completa",key="more_"+j["game_id"]+str(idx),
                     use_container_width=True,type="primary"):
            st.session_state.update({"jogo_id":j["game_id"],"goto":"🔍 Buscar"}); st.rerun()

def deal_card(j,i):
    pr=float(j.get("price") or 0); op=float(j.get("old_price") or 0)
    pc=j.get("discount_percent") or 0; st_=j.get("store","")
    cor=CORES.get(st_,"#90a4b0"); img=j.get("cover_url","")
    if pr==0: db="<span style='background:#1a1a1a;color:#fff;font-size:.72rem;font-weight:700;padding:2px 6px;border-radius:3px'>-100%</span>"; prc="#ef5350"
    elif pc>=90: db="<span style='background:#1a1a1a;color:#fff;font-size:.72rem;font-weight:700;padding:2px 6px;border-radius:3px'>-"+str(pc)+"%</span>"; prc="#ef5350"
    elif pc>0: db="<span style='background:#1a1a1a;color:#fff;font-size:.72rem;font-weight:700;padding:2px 6px;border-radius:3px'>-"+str(pc)+"%</span>"; prc="#fb8c00"
    else: db=""; prc="#37474f"
    flag=""
    if pc>=90: flag="<span style='background:#c62828;color:#fff;font-size:.6rem;font-weight:700;padding:1px 3px;border-radius:2px;margin-left:2px'>N</span>"
    elif pc>=75: flag="<span style='background:#e65100;color:#fff;font-size:.6rem;font-weight:700;padding:1px 3px;border-radius:2px;margin-left:2px'>H</span>"
    elif pc>=50: flag="<span style='background:#1565c0;color:#fff;font-size:.6rem;font-weight:700;padding:1px 3px;border-radius:2px;margin-left:2px'>S</span>"
    pr_s="R$ 0,00" if pr==0 else "R$ "+str(round(pr,2))
    op_s="R$ "+str(round(op,2)) if op>pr>0 else ""
    dot="<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:"+cor+";margin-right:4px;vertical-align:middle'></span>"
    ih=(("<img src='"+img+"' style='width:100px;height:56px;object-fit:cover;border-radius:4px;flex-shrink:0'>") if img
        else "<div style='width:100px;height:56px;background:#2a3f5a;border-radius:4px;flex-shrink:0'></div>")
    st.markdown("<div style='display:flex;gap:12px;align-items:center;background:#fff;"
                "border:1px solid #dde3e8;border-radius:6px;padding:8px 12px;margin-bottom:4px'>"
                +ih+
                "<div style='flex:1;min-width:0'>"
                "<div style='font-weight:600;font-size:.88rem;color:#1b2838;"
                "white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"+j["title"]+"</div>"
                "<div style='font-size:.72rem;color:#90a4b0;margin-top:3px;display:flex;gap:5px;align-items:center'>"
                "<span style='color:#78909c'>"+j.get("platform","")+"</span>"
                "<span>"+dot+st_+"</span></div></div>"
                "<div style='text-align:right;flex-shrink:0'>"
                "<div style='display:flex;gap:4px;align-items:center;justify-content:flex-end'>"
                +db+flag+
                "<span style='font-size:1rem;font-weight:700;color:"+prc+"'>"+pr_s+"</span></div>"
                "<div style='font-size:.75rem;color:#b0bec5'>"+st_+(" · "+op_s if op_s else "")+"</div>"
                "</div></div>",unsafe_allow_html=True)
    c1,c2=st.columns([5,1])
    with c1:
        if st.button("Ver detalhes",key="cd"+j["game_id"]+str(i),use_container_width=True):
            st.session_state.update({"jogo_id":j["game_id"],"goto":"🔍 Buscar"}); st.rerun()
    with c2:
        if st.button("⌄",key="ex"+j["game_id"]+str(i),use_container_width=True,help="Expandir"):
            k="open_"+j["game_id"]
            st.session_state[k]=not st.session_state.get(k,False)
    if st.session_state.get("open_"+j["game_id"]):
        with st.container(border=True):
            painel_expandido(j, i)

def detalhe(jg):
    # Deduplicar: manter menor preço por loja
    _all_ofs = [o for o in get_ofertas(jg["id"]) if o.get("price") is not None]
    _seen_lojas = {}
    for o in sorted(_all_ofs, key=lambda o: float(o["price"])):
        lj = o.get("store","")
        if lj not in _seen_lojas:
            _seen_lojas[lj] = o
    ofs = sorted(_seen_lojas.values(), key=lambda o: float(o["price"]))
    ca,ci=st.columns([1,2.5])
    with ca:
        if jg.get("cover_url"): st.image(jg["cover_url"],use_container_width=True)
        st.markdown("**"+jg["title"]+"**"); st.caption(jg["platform"])
        sid = get_session_id()
        in_wl = is_in_wishlist(sid, jg["id"])
        if in_wl:
            if st.button("❤️ Na Wishlist — Remover", key="wl_rem_"+jg["id"], use_container_width=True):
                remove_from_wishlist(sid, jg["id"])
                st.rerun()
        else:
            if st.button("🤍 Adicionar à Wishlist", key="wl_add_"+jg["id"], use_container_width=True):
                add_to_wishlist(sid, jg["id"])
                st.success("Adicionado à wishlist!")
                st.rerun()
    with ci:
        if not ofs: st.warning("Sem preços ainda."); return
        mn=float(ofs[0]["price"]); oids=[o["offer_id"] for o in ofs]
        hm=get_hmin(oids); low=hm is not None and mn<=hm+.01
        m1,m2,m3=st.columns(3)
        m1.metric("💰 Menor",R(mn))
        if ofs[0].get("old_price") and float(ofs[0]["old_price"])>mn:
            m2.metric("💸 Economia",R(float(ofs[0]["old_price"])-mn))
        if ofs[0].get("discount_percent"): m3.metric("🏷️",str(ofs[0]["discount_percent"])+"%")
        if low: st.success("🏷️ Mínimo histórico!")
        # Estatísticas 30/90 dias
        stats_map = get_price_stats(oids)
        if stats_map:
            best_stat = min(stats_map.values(), key=lambda x: float(x.get("price_min_ever") or 9999))
            s1,s2,s3 = st.columns(3)
            if best_stat.get("price_min_ever"):
                s1.metric("📉 Mínimo histórico", R(best_stat["price_min_ever"]))
            if best_stat.get("price_min_30d"):
                s2.metric("📅 Mín. 30 dias", R(best_stat["price_min_30d"]))
            if best_stat.get("price_min_90d"):
                s3.metric("📅 Mín. 90 dias", R(best_stat["price_min_90d"]))
        rows=""
        for i,o in enumerate(ofs):
            pr=float(o["price"]); df=pr-mn; dp=(df/mn*100) if mn>0 else 0
            cor=CORES.get(o["store"],"#90a4b0")
            disc=("-"+str(o["discount_percent"])+"%") if o.get("discount_percent") else "—"
            vs="✅ menor" if df==0 else "+"+R(df)+" ("+str(round(dp))+"% )"
            rows+=("<tr><td>"+MED.get(i,str(i+1)+"º")+"</td>"
                   "<td><span style='border-left:3px solid "+cor+";padding-left:6px'>"+o["store"]+"</span></td>"
                   "<td><b>"+R(pr)+"</b></td><td>"+disc+"</td>"
                   "<td style='color:#90a4b0;font-size:.8rem'>"+vs+"</td></tr>")
        st.markdown("<table class='rt'><thead><tr><th></th><th>Loja</th><th>Preço</th><th>Desc.</th><th>vs menor</th></tr></thead><tbody>"+rows+"</tbody></table>",unsafe_allow_html=True)
        st.markdown("")
        for o in ofs:
            pr=float(o["price"]); lb=("🆓 "+o["store"]+" — Grátis") if pr==0 else ("🛒 "+o["store"]+" — "+R(pr))
            st.link_button(lb,o.get("product_url","#"),use_container_width=True)
        # Ofertas Mercado Livre vinculadas (console/físico)
        ml_jogo = get_ml_por_jogo(jg["id"])
        if ml_jogo:
            st.markdown("**🎮 Também no Mercado Livre (físico):**")
            for m in ml_jogo:
                lbl = "🛒 "+m["titulo_ml"]
                if m.get("preco"): lbl += " — "+R(m["preco"])
                st.link_button(lbl, m["afiliado_url"], use_container_width=True)
        st.markdown("#### 📈 Histórico")
        mp={o["offer_id"]:o["store"] for o in ofs}
        h=get_hist(list(mp.keys()))
        if h:
            df2=pd.DataFrame(h); df2["captured_at"]=pd.to_datetime(df2["captured_at"])
            df2["Loja"]=df2["offer_id"].map(mp); df2["price"]=df2["price"].astype(float)
            dg=df2[df2["price"]>0]
            if not dg.empty:
                pv=dg.pivot_table(index="captured_at",columns="Loja",values="price",aggfunc="last")
                st.line_chart(pv)
                if hm: st.caption("Mínimo histórico: "+R(hm))
        else: st.caption("Histórico disponível após mais coletas.")
    st.divider()
    with st.expander("🔔 Criar alerta"):
        c1,c2=st.columns(2)
        em=c1.text_input("E-mail",key="ae")
        sg=round(mn*.8,2) if ofs and mn>0 else 100.
        al=c2.number_input("Preço alvo (R$)",min_value=1.,value=sg,step=5.)
        if st.button("🔔 Criar",type="primary"):
            if em and "@" in em:
                DB.table("alerts").insert({"user_email":em,"game_id":jg["id"],"target_price":float(al)}).execute()
                st.success("Alerta criado! Aviso quando "+jg["title"]+" < "+R(al))
            else: st.error("E-mail inválido.")

# ── FASE 1: Wishlist + Estatísticas + Mínimos históricos ─────────────────────

def get_session_id() -> str:
    """ID de sessão anônimo para wishlist sem login."""
    if "session_id" not in st.session_state:
        import uuid
        st.session_state["session_id"] = str(uuid.uuid4())
    return st.session_state["session_id"]

@st.cache_data(ttl=60)
def get_wishlist(session_id: str) -> list[dict]:
    try:
        rows = DB.table("wishlists").select(
            "game_id,target_price,added_at,games(title,cover_url,platform)"
        ).eq("session_id", session_id).order("added_at", desc=True).execute().data
        return rows
    except Exception:
        return []

def add_to_wishlist(session_id: str, game_id: str, target_price=None):
    try:
        DB.table("wishlists").upsert(
            {"session_id": session_id, "game_id": game_id, "target_price": target_price},
            on_conflict="session_id,game_id"
        ).execute()
        st.cache_data.clear()
        return True
    except Exception:
        return False

def remove_from_wishlist(session_id: str, game_id: str):
    try:
        DB.table("wishlists").delete()          .eq("session_id", session_id).eq("game_id", game_id).execute()
        st.cache_data.clear()
        return True
    except Exception:
        return False

def is_in_wishlist(session_id: str, game_id: str) -> bool:
    try:
        r = DB.table("wishlists").select("id")              .eq("session_id", session_id).eq("game_id", game_id).execute().data
        return len(r) > 0
    except Exception:
        return False

@st.cache_data(ttl=300)
def get_price_stats(offer_ids: list[str]) -> dict:
    """Retorna estatísticas de preço (min ever, 30d, 90d) por offer_id."""
    if not offer_ids:
        return {}
    try:
        rows = DB.table("price_statistics").select("*")                 .in_("offer_id", offer_ids).execute().data
        return {r["offer_id"]: r for r in rows}
    except Exception:
        return {}

@st.cache_data(ttl=300)
def get_historicos_hoje(limite=40) -> list[dict]:
    """Jogos no mínimo histórico hoje."""
    try:
        return DB.table("v_historicos_hoje").select("*").limit(limite).execute().data
    except Exception:
        return []

@st.cache_data(ttl=600)
def recalcular_stats_batch(offer_ids: list[str]) -> None:
    """Recalcula estatísticas de preço para um lote de ofertas."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    d30 = (now - timedelta(days=30)).isoformat()
    d90 = (now - timedelta(days=90)).isoformat()

    for oid in offer_ids:
        try:
            all_p = DB.table("prices").select("price")                      .eq("offer_id", oid).gt("price", 0).execute().data
            p30   = DB.table("prices").select("price")                      .eq("offer_id", oid).gt("price", 0)                      .gte("captured_at", d30).execute().data
            p90   = DB.table("prices").select("price")                      .eq("offer_id", oid).gt("price", 0)                      .gte("captured_at", d90).execute().data
            cur   = DB.table("prices").select("price")                      .eq("offer_id", oid).gt("price", 0)                      .order("captured_at", desc=True).limit(1).execute().data

            if not all_p:
                continue

            vals     = [float(r["price"]) for r in all_p]
            vals30   = [float(r["price"]) for r in p30]
            vals90   = [float(r["price"]) for r in p90]
            cur_val  = float(cur[0]["price"]) if cur else min(vals)
            offer_row = DB.table("game_store_offers").select("old_price")                          .eq("id", oid).execute().data
            orig = float(offer_row[0].get("old_price") or 0) if offer_row else 0
            disc_max = int((1 - min(vals)/orig)*100) if orig > 0 else 0

            DB.table("price_statistics").upsert({
                "offer_id":       oid,
                "price_current":  cur_val,
                "price_min_ever": min(vals),
                "price_min_30d":  min(vals30) if vals30 else None,
                "price_min_90d":  min(vals90) if vals90 else None,
                "price_avg_90d":  round(sum(vals90)/len(vals90), 2) if vals90 else None,
                "discount_max":   disc_max,
                "updated_at":     now.isoformat(),
            }, on_conflict="offer_id").execute()
        except Exception:
            continue


# ── MERCADO LIVRE: Afiliados (games + acessórios) ────────────────────────────

@st.cache_data(ttl=120)
def get_ml_ofertas(categoria=None) -> list[dict]:
    """Lista ofertas ML ativas (games e acessórios)."""
    try:
        q = DB.table("ml_afiliados").select("*").eq("ativo", True)
        if categoria:
            q = q.eq("categoria", categoria)
        return q.order("comissao_pct", desc=True).execute().data
    except Exception:
        return []

@st.cache_data(ttl=120)
def get_ml_por_jogo(game_id: str) -> list[dict]:
    """Ofertas ML vinculadas a um jogo específico do catálogo."""
    try:
        return (DB.table("ml_afiliados").select("*")
                .eq("game_id", game_id).eq("ativo", True)
                .order("comissao_pct", desc=True).execute().data)
    except Exception:
        return []

def add_ml_oferta(dados: dict) -> bool:
    try:
        DB.table("ml_afiliados").insert(dados).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def del_ml_oferta(oferta_id: str) -> bool:
    try:
        DB.table("ml_afiliados").delete().eq("id", oferta_id).execute()
        st.cache_data.clear()
        return True
    except Exception:
        return False


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='font-size:1.1rem;font-weight:700;color:#fff;padding:8px 0 4px'>🎮 GamePrice Brasil</div>",unsafe_allow_html=True)
    pag=st.radio("p",["🏠 Deals","🔍 Buscar","📚 Catálogo","🎮 Consoles","❤️ Wishlist","🏆 Históricos","📊 Stats","⚙️ Admin"],label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:.8rem;font-weight:700;color:#8fa3b1;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px'>🏪 Shop</div>",unsafe_allow_html=True)
    dots="".join(["<div style='padding:3px 0;font-size:.82rem'><span style='display:inline-block;width:8px;height:8px;border-radius:50%;background:"+LOJA_DOTS.get(l,"#888")+";margin-right:7px;vertical-align:middle'></span>"+l+"</div>" for l in list(LOJA_DOTS.keys())])
    st.markdown(dots,unsafe_allow_html=True)
    fl=st.selectbox("",["Todas"]+list(LOJA_DOTS.keys()),key="fl",label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:.8rem;font-weight:700;color:#8fa3b1;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px'>💰 Price</div>",unsafe_allow_html=True)
    fm=st.radio("pm",["Qualquer","Até R$ 5","Até R$ 25","Até R$ 50","Até R$ 100","Até R$ 150"],key="fm",label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:.8rem;font-weight:700;color:#8fa3b1;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px'>🏷️ Price Cut</div>",unsafe_allow_html=True)
    fd=st.radio("pc",["Qualquer","25% ou mais","50% ou mais","75% ou mais","90% ou mais"],key="fd",label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-size:.8rem;font-weight:700;color:#8fa3b1;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px'>🎮 Plataforma</div>",unsafe_allow_html=True)
    fp=st.radio("pp",PLAT,key="fp",label_visibility="collapsed")
    st.markdown("---")
    ep=get_epic(); cf=ep.get("current",[])
    if cf:
        st.markdown("<div style='font-size:.8rem;font-weight:700;color:#8fa3b1;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px'>🎁 Grátis na Epic</div>",unsafe_allow_html=True)
        for g in cf:
            st.markdown("<div style='font-size:.8rem;color:#c6d4df;padding:2px 0'>• "+g["title"]+"</div>",unsafe_allow_html=True)
            if g.get("end_date"): st.caption("até "+DT(g["end_date"]))
        st.link_button("Ver na Epic →","https://store.epicgames.com/pt-BR/free-games",use_container_width=True)
        st.markdown("---")
    st.caption("📊 "+str(n_jogos())+" jogos · Steam · GOG · Humble")

# ── NAVEGAÇÃO ─────────────────────────────────────────────────────────────────
if st.session_state.get("goto"):
    pag=st.session_state.pop("goto")

mg=[0.5,7,0.5]

# ══════════════════════════════════════════════════════════════════════════════
if pag=="🏠 Deals":
    _,C,_=st.columns(mg)
    with C:
        ep=get_epic(); cf=ep.get("current",[]); nf=ep.get("next",[])
        if cf or nf:
            st.markdown('<div class="sh">🎁 Grátis na Epic esta semana</div>',unsafe_allow_html=True)
            cols=st.columns(min(len(cf)+len(nf),4))
            for i,g in enumerate(cf):
                with cols[i%4]:
                    if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                    end=DT(g["end_date"]) if g.get("end_date") else ""
                    st.markdown("**"+g["title"]+"**")
                    st.markdown("<span style='background:#1565c0;color:#fff;font-size:.68rem;font-weight:700;padding:2px 6px;border-radius:3px'>GRÁTIS</span> <span style='font-size:.7rem;color:#888'>até "+end+"</span>",unsafe_allow_html=True)
                    st.link_button("Pegar grátis →","https://store.epicgames.com/pt-BR/free-games",use_container_width=True)
            for i,g in enumerate(nf):
                with cols[(len(cf)+i)%4]:
                    if g.get("image_url"): st.image(g["image_url"],use_container_width=True)
                    st.markdown("**"+g["title"]+"**")
                    st.markdown("<span style='background:#e65100;color:#fff;font-size:.68rem;font-weight:700;padding:2px 6px;border-radius:3px'>EM BREVE</span>",unsafe_allow_html=True)
            st.divider()
        pm=None
        if fm!="Qualquer": pm=float(fm.replace("Até R$ ",""))
        disc_min=0
        if fd!="Qualquer": disc_min=int(fd.split("%")[0])
        st.markdown('<div class="sh">🔥 Melhores deals agora</div>',unsafe_allow_html=True)
        ds=get_deals(fl,fp,disc_min,60)
        if pm: ds=[d for d in ds if float(d.get("price") or 0)<=pm]
        if not ds: st.info("Nenhum deal com esses filtros.")
        else:
            st.caption(str(len(ds))+" deals")
            for i,j in enumerate(ds): deal_card(j,i)

elif pag=="🔍 Buscar":
    _,C,_=st.columns(mg)
    with C:
        jp=None
        if "jogo_id" in st.session_state:
            r=DB.table("games").select("*").eq("id",st.session_state["jogo_id"]).execute().data
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
            tit={j["title"]+" ("+j["platform"]+")":j for j in js}
            jg=js[0] if len(js)==1 else tit[st.selectbox("Selecione",list(tit.keys()))]
        else: jg=jp
        st.divider(); detalhe(jg)

elif pag=="📚 Catálogo":
    _,C,_=st.columns(mg)
    with C:
        c1,c2,c3=st.columns([2,1,1])
        nm=c1.text_input("🔍 Nome",key="cn",placeholder="ex.: Hades, Elden...")
        pt=c2.selectbox("Plataforma",PLAT,key="cp")
        od=c3.selectbox("Ordenar",["A-Z","Menor preço","Maior desconto"],key="co")
        q=DB.table("v_game_offers").select("game_id,title,platform,cover_url,price,discount_percent").order("title").limit(500)
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
        st.caption(str(len(jc))+" jogos")
        for rs in range(0,len(jc),5):
            cols=st.columns(5)
            for ci,j in enumerate(jc[rs:rs+5]):
                with cols[ci]:
                    if j.get("cover_url"): st.image(j["cover_url"],use_container_width=True)
                    pc=j.get("discount_percent") or 0
                    bx=("<span style='background:#3a8a3a;color:#fff;font-size:.65rem;padding:1px 4px;border-radius:3px'>-"+str(pc)+"%</span>") if pc else ""
                    st.markdown("<div style='font-size:.78rem;font-weight:600;color:#1b2838;line-height:1.2;margin-top:3px'>"+j["title"]+"</div>"
                                "<div style='color:#3a8a3a;font-weight:700;font-size:.82rem'>"+R(j.get("price"))+" "+bx+"</div>",unsafe_allow_html=True)
                    if st.button("Ver",key="ct"+j["game_id"]+str(rs+ci),use_container_width=True):
                        st.session_state.update({"jogo_id":j["game_id"],"goto":"🔍 Buscar"}); st.rerun()

elif pag=="❤️ Wishlist":
    _,C,_=st.columns(mg)
    with C:
        sid=get_session_id()
        st.subheader("❤️ Minha Wishlist")
        wl=get_wishlist(sid)
        if not wl:
            st.info("Sua wishlist está vazia. Busque um jogo e clique em '🤍 Adicionar à Wishlist'.")
        else:
            st.caption(str(len(wl))+" jogos na wishlist")
            for item in wl:
                ginfo=item.get("games") or {}
                gid=item["game_id"]
                c1,c2,c3=st.columns([1,3,1])
                with c1:
                    if ginfo.get("cover_url"): st.image(ginfo["cover_url"],use_container_width=True)
                with c2:
                    st.markdown("**"+ginfo.get("title","?")+"**")
                    st.caption(ginfo.get("platform",""))
                    # Buscar melhor preço atual
                    ofs_wl=[o for o in get_ofertas(gid) if o.get("price") is not None]
                    if ofs_wl:
                        mn_wl=min(float(o["price"]) for o in ofs_wl)
                        tp=item.get("target_price")
                        if tp and mn_wl<=float(tp):
                            st.success("🎯 Preço alvo atingido! "+R(mn_wl))
                        else:
                            st.write("Menor preço: **"+R(mn_wl)+"**")
                            if tp: st.caption("Alvo: "+R(tp))
                with c3:
                    if st.button("🗑️",key="wl_del_"+gid,help="Remover"):
                        remove_from_wishlist(sid,gid); st.rerun()
                    if st.button("🔍",key="wl_ver_"+gid,help="Ver jogo"):
                        st.session_state.update({"jogo_id":gid,"goto":"🔍 Buscar"}); st.rerun()
                st.divider()

elif pag=="🏆 Históricos":
    _,C,_=st.columns(mg)
    with C:
        st.subheader("🏆 Mínimos históricos atingidos")
        st.caption("Jogos no menor preço de todos os tempos agora")
        hist_hoje=get_historicos_hoje(40)
        if not hist_hoje:
            st.info("Nenhum mínimo histórico detectado. Os dados são calculados após alguns ciclos do worker.")
            st.caption("Execute: Actions → update-prices → Run workflow")
        else:
            st.caption(str(len(hist_hoje))+" jogos no mínimo histórico")
            for h in hist_hoje:
                c1,c2,c3=st.columns([1,3,1])
                with c1:
                    if h.get("cover_url"): st.image(h["cover_url"],use_container_width=True)
                with c2:
                    st.markdown("**"+h["title"]+"**")
                    st.caption(h.get("platform","")+" · "+h.get("store",""))
                    st.markdown(
                        "<span style='background:#c62828;color:#fff;font-size:.7rem;"
                        "font-weight:700;padding:2px 6px;border-radius:3px'>🏆 MÍNIMO HISTÓRICO</span>",
                        unsafe_allow_html=True)
                with c3:
                    pr_h=float(h.get("price_current") or 0)
                    st.markdown("**"+R(pr_h)+"**")
                    if h.get("discount_max"):
                        st.caption("-"+str(h["discount_max"])+"%")
                st.divider()

elif pag=="🎮 Consoles":
    _,C,_=st.columns(mg)
    with C:
        st.subheader("🎮 Games & Acessórios — Mercado Livre")
        st.caption("Ofertas de jogos físicos de console e acessórios gamer")
        ofertas_ml = get_ml_ofertas()
        if not ofertas_ml:
            st.info("Nenhuma oferta cadastrada ainda. Use a aba ⚙️ Admin para adicionar.")
        else:
            # Filtro por categoria
            cat = st.radio("Categoria", ["Tudo","🎮 Games","🎧 Acessórios"],
                           horizontal=True, label_visibility="collapsed")
            filtrados = ofertas_ml
            if cat == "🎮 Games":
                filtrados = [o for o in ofertas_ml if o.get("categoria")=="game"]
            elif cat == "🎧 Acessórios":
                filtrados = [o for o in ofertas_ml if o.get("categoria")=="acessorio"]
            st.caption(str(len(filtrados))+" ofertas")
            for o in filtrados:
                c1,c2,c3 = st.columns([1,3,1.2])
                with c1:
                    if o.get("imagem_url"):
                        st.image(o["imagem_url"], use_container_width=True)
                with c2:
                    st.markdown("**"+o["titulo_ml"]+"**")
                    meta = []
                    if o.get("plataforma"): meta.append(o["plataforma"])
                    if o.get("comissao_pct"): meta.append("💰 "+str(o["comissao_pct"])+"% comissão")
                    st.caption(" · ".join(meta))
                with c3:
                    if o.get("preco"):
                        st.markdown("**"+R(o["preco"])+"**")
                    st.link_button("🛒 Comprar no ML", o["afiliado_url"],
                                   use_container_width=True, type="primary")
                st.divider()

elif pag=="⚙️ Admin":
    _,C,_=st.columns(mg)
    with C:
        st.subheader("⚙️ Admin — Ofertas Mercado Livre")
        # Proteção por senha
        senha = st.text_input("Senha de admin", type="password", key="admin_pw")
        senha_correta = st.secrets.get("admin", {}).get("senha", "")
        if not senha:
            st.info("Digite a senha para acessar o painel de cadastro.")
            st.stop()
        if senha != senha_correta:
            st.error("Senha incorreta.")
            st.stop()
        st.success("✓ Acesso liberado")

        st.markdown("### ➕ Adicionar oferta ML")
        st.caption("No app do ML: abra o produto → Compartilhar como afiliado → "
                   "Copiar link (cola em URL) e Copiar ID (cola em ID).")

        col1, col2 = st.columns(2)
        with col1:
            titulo = st.text_input("Título do produto", key="ml_tit",
                                   placeholder="ex.: Final Fantasy VII Rebirth PS5")
            categoria = st.selectbox("Categoria", ["game","acessorio"], key="ml_cat")
            plataforma = st.selectbox("Plataforma",
                                      ["PS5","PS4","XBOX","SWITCH","PC","Multi","-"], key="ml_plat")
        with col2:
            preco = st.number_input("Preço (R$)", min_value=0.0, step=10.0, key="ml_preco")
            comissao = st.number_input("Comissão (%)", min_value=0, max_value=30,
                                       value=16, key="ml_com")
        url = st.text_input("Link de afiliado (meli.la/...)", key="ml_url",
                            placeholder="https://meli.la/xxxxx")
        ml_id = st.text_input("ID do produto (MLB...)", key="ml_id_in",
                             placeholder="MLB1234567 (opcional)")
        imagem = st.text_input("URL da imagem (opcional)", key="ml_img")

        if st.button("💾 Salvar oferta", type="primary"):
            if not titulo or not url:
                st.error("Título e link são obrigatórios.")
            else:
                dados = {
                    "titulo_ml": titulo, "categoria": categoria,
                    "plataforma": plataforma if plataforma!="-" else None,
                    "preco": preco if preco>0 else None,
                    "comissao_pct": comissao, "afiliado_url": url,
                    "ml_id": ml_id or None, "imagem_url": imagem or None,
                }
                if add_ml_oferta(dados):
                    st.success("Oferta salva! ✓")
                    st.rerun()

        st.divider()
        st.markdown("### 📋 Ofertas cadastradas")
        ofertas = get_ml_ofertas()
        if not ofertas:
            st.caption("Nenhuma oferta ainda.")
        else:
            for o in ofertas:
                c1,c2 = st.columns([5,1])
                with c1:
                    st.markdown("**"+o["titulo_ml"]+"** — "+R(o.get("preco"))
                               +" · "+str(o.get("comissao_pct",0))+"%")
                    st.caption(o["afiliado_url"])
                with c2:
                    if st.button("🗑️", key="mldel_"+o["id"]):
                        del_ml_oferta(o["id"]); st.rerun()

else:
    _,C,_=st.columns(mg)
    with C:
        st.subheader("📊 Estatísticas")
        s=get_stats()
        c1,c2,c3=st.columns(3)
        c1.metric("🎮 Jogos","{:,}".format(s["jogos"]))
        c2.metric("💰 Preços","{:,}".format(s["precos"]))
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
            top=get_deals(lim=10)
            if top:
                st.dataframe(pd.DataFrame([{"Jogo":j["title"],"Loja":j.get("store",""),
                    "Preço":R(j.get("price")),"Desc":str(j.get("discount_percent",0))+"%"}
                    for j in top]),hide_index=True,use_container_width=True)
        ep=get_epic(); c1,c2=st.columns(2)
        c1.metric("Grátis Epic",len(ep.get("current",[])))
        c2.metric("Em breve",len(ep.get("next",[])))
