import csv, math, re
from pathlib import Path

_STATS = {}

def _norm(s):
    s=(s or "").lower().strip()
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return " ".join(s.split())

def _key(home,away):
    return _norm(home)+"||"+_norm(away)

def _f(v):
    try:
        if v is None or v=="": return None
        return float(str(v).replace(",","."))
    except Exception:
        return None

def _ints(v):
    if v is None: return []
    out=[]
    for x in re.split(r"[;|,\s]+",str(v).strip()):
        if not x: continue
        try: out.append(int(float(x)))
        except: pass
    return out

def load_stats_csv(path):
    global _STATS
    rows={}
    with open(path,"r",encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            home=r.get("home","").strip(); away=r.get("away","").strip()
            if home and away:
                rows[_key(home,away)]=r
    _STATS=rows
    return len(rows)

def set_stats_dict(rows):
    global _STATS
    _STATS={}
    for st in rows:
        home=st.get("home",""); away=st.get("away","")
        if home and away:
            _STATS[_key(home,away)]=st
    return len(_STATS)

def stats_count():
    return len(_STATS)

def merge_stats_dict(rows):
    """Merge automatic real history without overwriting user-imported rows."""
    added=0
    for st in rows:
        home=st.get("home",""); away=st.get("away","")
        if not home or not away: continue
        k=_key(home,away)
        if k not in _STATS:
            _STATS[k]=st; added+=1
    return added

def get_stats_for_match(home,away):
    """Read-only access for auxiliary engines such as GOLBET."""
    return _STATS.get(_key(home,away))

def _poisson_pmf(lam,k):
    if lam is None or lam < 0: return 0.0
    return math.exp(-lam)*(lam**k)/math.factorial(k)

def poisson_method(r,st):
    hgf=_f(st.get("home_gf_avg")); hga=_f(st.get("home_ga_avg"))
    agf=_f(st.get("away_gf_avg")); aga=_f(st.get("away_ga_avg"))
    if None in (hgf,hga,agf,aga):
        return None

    # Coerente con il foglio: medie gol fatti/subiti delle due squadre
    lam_h=max(0.05,(hgf+aga)/2)
    lam_a=max(0.05,(agf+hga)/2)

    maxg=8
    mat=[[ _poisson_pmf(lam_h,i)*_poisson_pmf(lam_a,j)
           for j in range(maxg+1)] for i in range(maxg+1)]

    p1=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i>j)
    px=sum(mat[i][i] for i in range(maxg+1))
    p2=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i<j)
    po15=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i+j>=2)
    po25=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i+j>=3)
    pu35=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i+j<=3)
    pgg=sum(mat[i][j] for i in range(1,maxg+1) for j in range(1,maxg+1))

    probs={"1":p1,"X":px,"2":p2,"OVER 1,5":po15,"OVER 2,5":po25,
           "UNDER 3,5":pu35,"GG":pgg}
    pick=max(("1","X","2"), key=lambda k:probs[k])
    score=round(probs[pick]*100)

    # Soglie presenti nel foglio "il Software per i pronostici":
    # 1X2 >70%; DC >85%; O/U e GG >70%.
    markets=[]
    for k in ("1","X","2"):
        if probs[k]*100>70: markets.append((k,round(probs[k]*100)))
    if (p1+px)*100>85: markets.append(("1X",round((p1+px)*100)))
    if (px+p2)*100>85: markets.append(("X2",round((px+p2)*100)))
    if (p1+p2)*100>85: markets.append(("12",round((p1+p2)*100)))
    if po15*100>70: markets.append(("OVER 1,5",round(po15*100)))
    if po25*100>70: markets.append(("OVER 2,5",round(po25*100)))
    if pu35*100>70: markets.append(("UNDER 3,5",round(pu35*100)))
    if pgg*100>70: markets.append(("GG",round(pgg*100)))

    exact=[]
    for i in range(6):
        for j in range(6):
            exact.append((mat[i][j],f"{i}-{j}"))
    exact=sorted(exact,reverse=True)[:3]

    return {
        "method":"POISSON","pick":pick,"score":score,
        "markets":markets,
        "reason":(("STIMA MERCATO | " if st.get("stats_source")=="STIMA MERCATO" else "") + f"λ home {lam_h:.2f} | λ away {lam_a:.2f} | 1 {p1*100:.1f}% X {px*100:.1f}% 2 {p2*100:.1f}%"),
        "exact":[(x[1],round(x[0]*100,1)) for x in exact]
    }

def valuebet_method(r,st):
    hp=_f(st.get("home_over25_pct")); ap=_f(st.get("away_over25_pct"))
    if hp is None or ap is None: return None
    real_over=(hp+ap)/2
    real_under=100-real_over
    raw=r.get("raw",{}) or {}
    qo=_f(st.get("over25_odds")) or _f(raw.get("over_price_current"))
    qu=_f(st.get("under25_odds")) or _f(raw.get("under_price_current"))
    if not qo or not qu: return None

    book_over=100/qo
    book_under=100/qu
    vo=real_over-book_over
    vu=real_under-book_under
    # Foglio: Value Bet > 5%
    if max(vo,vu) <= 5:
        return {"method":"VALUE BET","pick":"NO BET","score":0,
                "reason":f"Over {vo:+.1f}% | Under {vu:+.1f}% (soglia +5%)"}
    if vo>=vu:
        return {"method":"VALUE BET","pick":"OVER 2,5","score":min(95,round(65+vo)),
                "reason":(("STIMA MERCATO | " if st.get("stats_source")=="STIMA MERCATO" else "") + f"Real Over {real_over:.1f}% vs bookmaker {book_over:.1f}% = {vo:+.1f}%")}
    return {"method":"VALUE BET","pick":"UNDER 2,5","score":min(95,round(65+vu)),
            "reason":(("STIMA MERCATO | " if st.get("stats_source")=="STIMA MERCATO" else "") + f"Real Under {real_under:.1f}% vs bookmaker {book_under:.1f}% = {vu:+.1f}%")}

def _market_1x2_probs(r):
    raw=r.get("raw",{}) or {}
    vals=[]
    for k in ("ml_home_current","ml_draw_current","ml_away_current"):
        q=_f(raw.get(k))
        if not q or q<=1: return None
        vals.append(1/q)
    s=sum(vals)
    return [x/s for x in vals] if s else None

def _pois_outcomes(lh,la,maxg=9):
    mat=[[ _poisson_pmf(lh,i)*_poisson_pmf(la,j)
           for j in range(maxg+1)] for i in range(maxg+1)]
    p1=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i>j)
    px=sum(mat[i][i] for i in range(maxg+1))
    p2=sum(mat[i][j] for i in range(maxg+1) for j in range(maxg+1) if i<j)
    return p1,px,p2

def over15_method(r,st):
    hg=_ints(st.get("home_last10_for")); hc=_ints(st.get("home_last10_against"))
    ag=_ints(st.get("away_last10_for")); ac=_ints(st.get("away_last10_against"))
    if min(len(hg),len(hc),len(ag),len(ac)) >= 5:
        avgs=[sum(hg)/len(hg),sum(hc)/len(hc),sum(ag)/len(ag),sum(ac)/len(ac)]
        flags=[x>1.5 for x in avgs]; n=sum(flags)
        pick="OVER 1,5" if n>=3 else "NO BET"
        score=0 if pick=="NO BET" else min(95,70+n*6)
        return {"method":"OVER 1,5 PREDICT","pick":pick,"score":score,
                "reason":"medie GF/GS: "+" / ".join(f"{x:.2f}" for x in avgs)+f" | conferme {n}/4"}

    # Automatic fallback from market-derived Poisson parameters.
    if st.get("stats_source")=="STIMA MERCATO":
        hgf=_f(st.get("home_gf_avg")); aga=_f(st.get("away_ga_avg"))
        agf=_f(st.get("away_gf_avg")); hga=_f(st.get("home_ga_avg"))
        if None in (hgf,aga,agf,hga): return None
        lh=max(.05,(hgf+aga)/2); la=max(.05,(agf+hga)/2)
        lam=lh+la
        p15=1-math.exp(-lam)*(1+lam)
        score=round(p15*100)
        pick="OVER 1,5" if score>=70 else "NO BET"
        return {"method":"OVER 1,5 PREDICT","pick":pick,
                "score":score if pick!="NO BET" else 0,
                "reason":f"STIMA MERCATO | P(Over 1,5) {score}% | λ totale {lam:.2f}"}
    return None

def fissa_method(r,st):
    hgf=_ints(st.get("home_last5_for")); hga=_ints(st.get("home_last5_against"))
    agf=_ints(st.get("away_last5_for")); aga=_ints(st.get("away_last5_against"))
    if min(len(hgf),len(hga),len(agf),len(aga)) >= 5:
        H11=sum(hgf[:5]); I11=sum(hga[:5]); H18=sum(agf[:5]); I18=sum(aga[:5])
        H19=H11+H18; C22=(H11+H19)/10; D22=(I18+I11)/10
        C23=C22*2; D23=D22*2
        p1=C22>D23; p2=D22>C23
        pick="1" if p1 else "2" if p2 else "NO BET"
        gap=max(C22-D23,D22-C23,0)
        score=0 if pick=="NO BET" else min(90,round(62+gap*10))
        return {"method":"FISSA BET","pick":pick,"score":score,
                "reason":f"C22={C22:.2f} D23={D23:.2f} | D22={D22:.2f} C23={C23:.2f}"}

    # Market proxy: only a genuinely strong no-vig 1X2 favourite qualifies.
    if st.get("stats_source")=="STIMA MERCATO":
        pr=_market_1x2_probs(r)
        if not pr:return None
        ph,px,pa=pr
        if ph>=.58 and ph-pa>=.18: pick,prob="1",ph
        elif pa>=.58 and pa-ph>=.18: pick,prob="2",pa
        else: pick,prob="NO BET",max(ph,pa)
        score=0 if pick=="NO BET" else min(90,round(prob*100+12))
        return {"method":"FISSA BET","pick":pick,"score":score,
                "reason":f"STIMA MERCATO | 1 {ph*100:.1f}% X {px*100:.1f}% 2 {pa*100:.1f}% | soglia favorita 58%"}
    return None

def ht_method(r,st):
    vals=[_f(st.get(x)) for x in (
        "home_ht_w","home_ht_d","home_ht_l","away_ht_w","away_ht_d","away_ht_l")]
    if not any(v is None for v in vals):
        hw,hd,hl,aw,ad,al=vals
        total=hw+hd+hl+aw+ad+al
        if total<=0:return None
        p1=(hw+al)/total*100; px=(hd+ad)/total*100; p2=(aw+hl)/total*100
        probs={"1 HT":p1,"X HT":px,"2 HT":p2}
        pick=max(probs,key=probs.get); score=round(probs[pick])
        return {"method":"PRIMO TEMPO","pick":pick,"score":score,
                "reason":f"1HT {p1:.1f}% | XHT {px:.1f}% | 2HT {p2:.1f}%"}

    # First-half proxy from market-derived full-time lambdas.
    # 45% of expected goals is a conservative first-half share.
    if st.get("stats_source")=="STIMA MERCATO":
        hgf=_f(st.get("home_gf_avg")); aga=_f(st.get("away_ga_avg"))
        agf=_f(st.get("away_gf_avg")); hga=_f(st.get("home_ga_avg"))
        if None in (hgf,aga,agf,hga):return None
        lh=max(.03,((hgf+aga)/2)*.45); la=max(.03,((agf+hga)/2)*.45)
        p1,px,p2=_pois_outcomes(lh,la)
        probs={"1 HT":p1,"X HT":px,"2 HT":p2}
        pick=max(probs,key=probs.get); score=round(probs[pick]*100)
        # Avoid weak automatic first-half tips.
        if score<45: pick="NO BET"; score=0
        return {"method":"PRIMO TEMPO","pick":pick,"score":score,
                "reason":f"STIMA MERCATO | 1HT {p1*100:.1f}% XHT {px*100:.1f}% 2HT {p2*100:.1f}%"}
    return None

def _same_family(a,b):
    a=(a or "").upper(); b=(b or "").upper()
    if a==b:return True
    if a in ("1","X","2") and b in ("1","X","2"): return a==b
    if "OVER 2,5" in a and "OVER 2,5" in b:return True
    if "GG" in a and "GG" in b:return True
    if "OVER 1,5" in a and ("OVER 1,5" in b or "OVER 2,5" in b):return True
    return False

def apply_multimethod(rows):
    for r in rows:
        st=_STATS.get(_key(r.get("home"),r.get("away")))
        methods=[]
        if st:
            for fn in (poisson_method,valuebet_method,over15_method,fissa_method,ht_method):
                try:
                    x=fn(r,st)
                    if x: methods.append(x)
                except Exception as e:
                    methods.append({"method":fn.__name__,"pick":"ERRORE","score":0,"reason":str(e)})

        # GOLBET v1.0: statistical signals from the latest six matches.
        if r.get("golbet_available"):
            gpicks=list(r.get("golbet_signals",[]) or [])
            dc=r.get("golbet_dc")
            if dc:
                methods.append({"method":"GOLBET RATING","pick":dc,"score":0,
                                "reason":f"Rating {r.get('golbet_rating')} | rischioso {r.get('golbet_risky_1x2') or '--'}"})
            for gpick in gpicks:
                methods.append({"method":"GOLBET","pick":gpick,"score":0,
                                "reason":f"G HOME {r.get('golbet_g_home'):.2f} | G AWAY {r.get('golbet_g_away'):.2f} | G TOTAL {r.get('golbet_g_total'):.2f}"})

        # Motori esistenti come segnali separati, non modificati.
        if r.get("pick") and r.get("pick")!="DA VERIFICARE":
            methods.insert(0,{"method":"BETPROFESSIONAL GOAL","pick":r.get("pick"),
                              "score":r.get("score",0),
                              "reason":"Motore GOAL multisource 2.5"})
        if r.get("pick_1x2") and r.get("pick_1x2")!="NO BET":
            methods.insert(0,{"method":"BETPROFESSIONAL 1X2","pick":r.get("pick_1x2"),
                              "score":r.get("score_1x2",0),
                              "reason":"Motore 1X2 multisource 2.5"})

        r["method_status"]={
            "POISSON":"OK" if any(m.get("method")=="POISSON" for m in methods) else "DATI INSUFFICIENTI",
            "VALUE BET":"OK" if any(m.get("method")=="VALUE BET" for m in methods) else "DATI INSUFFICIENTI",
            "OVER 1,5 PREDICT":"OK" if any(m.get("method")=="OVER 1,5 PREDICT" for m in methods) else "DATI INSUFFICIENTI",
            "FISSA BET":"OK" if any(m.get("method")=="FISSA BET" for m in methods) else "DATI INSUFFICIENTI",
            "PRIMO TEMPO":"OK" if any(m.get("method")=="PRIMO TEMPO" for m in methods) else "DATI INSUFFICIENTI",
            "GOLBET":"OK" if r.get("golbet_available") else "DATI INSUFFICIENTI",
        }
        r["methods"]=methods
        r["poisson"]=next((m for m in methods if m["method"]=="POISSON"),None)
        r["valuebet"]=next((m for m in methods if m["method"]=="VALUE BET"),None)
        r["over15"]=next((m for m in methods if m["method"]=="OVER 1,5 PREDICT"),None)
        r["fissabet"]=next((m for m in methods if m["method"]=="FISSA BET"),None)
        r["ht"]=next((m for m in methods if m["method"]=="PRIMO TEMPO"),None)

        # Consenso per il miglior pick tra metodi disponibili.
        candidates=[m for m in methods if m.get("pick") not in ("NO BET","ERRORE","")]
        best=None
        for c in candidates:
            supporters=[m for m in candidates if _same_family(c["pick"],m["pick"])]
            consensus=len(supporters)
            avg=round(sum(m.get("score",0) for m in supporters)/consensus) if consensus else 0
            # priorità: numero metodi, poi media score
            key=(consensus,avg,c.get("score",0))
            if best is None or key>best[0]:
                best=(key,c["pick"],supporters,avg)
        if best:
            _,pick,supporters,avg=best
            n=len(supporters)
            r["consensus_pick"]=pick
            r["consensus_n"]=n
            r["consensus_score"]=min(95,round(avg + max(0,n-1)*4))
            r["consensus_methods"]=[m["method"] for m in supporters]
            r["consensus_reason"]=" + ".join(r["consensus_methods"])
        else:
            r["consensus_pick"]="NO BET"
            r["consensus_n"]=0
            r["consensus_score"]=0
            r["consensus_methods"]=[]
            r["consensus_reason"]="nessun metodo disponibile"

    return rows
