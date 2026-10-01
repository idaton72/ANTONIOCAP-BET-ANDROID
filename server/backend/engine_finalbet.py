
def _score(v):
    try:return int(round(float(v or 0)))
    except:return 0

def _family(pick):
    p=(pick or "").upper().strip()
    if p in ("1","X","2"): return ("1X2",p)
    if p in ("1 HT","X HT","2 HT"): return ("1T",p)
    if "GG + OVER 2,5" in p:return ("GOAL","GG + OVER 2,5")
    if p=="GG":return ("GOAL","GG")
    if "OVER 2,5" in p:return ("TOTAL","OVER 2,5")
    if "UNDER 2,5" in p:return ("TOTAL","UNDER 2,5")
    if "OVER 1,5" in p:return ("TOTAL","OVER 1,5")
    if "UNDER 3,5" in p:return ("TOTAL","UNDER 3,5")
    return ("ALTRO",p)

def _compatible(a,b):
    fa,pa=_family(a); fb,pb=_family(b)
    if fa=="1X2" or fb=="1X2": return fa==fb and pa==pb
    if fa=="1T" or fb=="1T": return fa==fb and pa==pb
    if pa==pb:return True
    # Goal families: these are supporting, not identical, signals.
    if "OVER 2,5" in pa and "OVER 2,5" in pb:return True
    if pa=="GG + OVER 2,5" and pb in ("GG","OVER 2,5"):return True
    if pb=="GG + OVER 2,5" and pa in ("GG","OVER 2,5"):return True
    if pa=="OVER 1,5" and ("OVER 2,5" in pb or "GG + OVER 2,5" in pb):return True
    if pb=="OVER 1,5" and ("OVER 2,5" in pa or "GG + OVER 2,5" in pa):return True
    return False

def _market_name(pick,method):
    p=(pick or "").upper()
    if p in ("1","X","2"):return "1X2"
    if p in ("1 HT","X HT","2 HT"):return "PRIMO TEMPO"
    if "GG + OVER" in p:return "GG + OVER"
    if p=="GG":return "GG"
    if "OVER" in p or "UNDER" in p:return "OVER/UNDER"
    return method

def _estimated(method):
    reason=(method.get("reason") or "").upper()
    return "STIMA MERCATO" in reason

def _method_candidates(r):
    out=[]
    # Core BetProfessional signals are market/movement signals and remain independent
    # of the statistical estimator.
    if r.get("pick_1x2") not in (None,"","NO BET") and _score(r.get("score_1x2"))>=50:
        out.append({"method":"BETPROFESSIONAL 1X2","pick":r["pick_1x2"],
                    "score":_score(r["score_1x2"]),"estimated":False})
    if r.get("pick") not in (None,"","DA VERIFICARE") and _score(r.get("score"))>=50:
        out.append({"method":"BETPROFESSIONAL GOAL","pick":r["pick"],
                    "score":_score(r["score"]),"estimated":False})

    for m in r.get("methods",[]) or []:
        name=m.get("method","")
        # Do not duplicate the two Skianta signals already inserted.
        if name.startswith("BETPROFESSIONAL"):continue
        pick=m.get("pick")
        sc=_score(m.get("score"))
        if not pick or pick in ("NO BET","ERRORE") or sc<=0:continue
        if name=="POISSON":
            # Poisson can expose stronger side markets than its headline 1X2 pick.
            markets=m.get("markets",[]) or []
            for pp,ss in markets:
                out.append({"method":"POISSON","pick":pp,"score":_score(ss),
                            "estimated":_estimated(m)})
            # only add headline if not already represented
            if not any(pp==pick for pp,_ in markets):
                out.append({"method":"POISSON","pick":pick,"score":sc,
                            "estimated":_estimated(m)})
        else:
            out.append({"method":name,"pick":pick,"score":sc,
                        "estimated":_estimated(m)})
    return out

def _source_support(r,pick):
    fam,_=_family(pick)
    src=[]
    if fam=="1X2":
        src=list(r.get("multisource_1x2_support",[]) or r.get("confirmations_1x2",[]) or [])
    elif fam in ("GOAL","TOTAL"):
        src=list(r.get("multisource_goal_support",[]) or r.get("confirmations",[]) or [])
    # preserve order / unique
    seen=set(); clean=[]
    for x in src:
        if x and x not in seen:
            seen.add(x);clean.append(x)
    return clean

def _conflicts(r,pick):
    fam,_=_family(pick)
    return list(r.get("multisource_1x2_conflict",[]) or []) if fam=="1X2" else []


def _afr_adjustment(r,pick):
 p=(pick or "").upper().replace(",",".")
 for a in r.get("afootballreport") or []:
  ap=(a.get("pick") or "").upper().replace(",",".");m=a.get("market")
  ok=(p in ("1","X","2") and m=="1X2" and (ap==p or p in ap)) or (p=="GG" and m=="BTTS") or ("OVER 2.5" in p and m=="OU" and ap=="OVER 2.5") or ("OVER 1.5" in p and m=="OU" and ap=="OVER 1.5")
  if ok:return 5,f"AFR conferma {ap} +5"
 return 0,"AFR: nessuna conferma"
def _footystats_adjustment(r,pick):
 st=r.get("footystats") or {};p=(pick or "").upper().replace(",",".")
 if not st:return 0,"FootyStats: dato non disponibile"
 if "OVER 2.5" in p and st.get("over25") is not None:
  v=st["over25"];a=6 if v>=65 else 3 if v>=55 else -4 if v<45 else 0;return a,f"FootyStats O2.5={v:.0f}% ({a:+d})"
 if p=="GG" and st.get("btts") is not None:
  v=st["btts"];a=5 if v>=60 else 2 if v>=52 else -4 if v<42 else 0;return a,f"FootyStats BTTS={v:.0f}% ({a:+d})"
 if ("1T" in p or "PRIMO" in p) and st.get("avg_fh_goals") is not None:
  v=st["avg_fh_goals"];a=4 if v>=1.35 else 2 if v>=1.05 else -2 if v<0.70 else 0;return a,f"FootyStats media gol 1T={v:.2f} ({a:+d})"
 return 0,"FootyStats: statistica non applicabile"


def _soccerstats247_adjustment(r,pick):
    st=r.get("soccerstats247") or {};p=(pick or "").upper().replace(",",".")
    if not st:return 0,"SoccerStats247: dato non disponibile"
    if "OVER 2.5" in p and st.get("over25") is not None:
        v=st["over25"];a=5 if v>=65 else 2 if v>=55 else -4 if v<45 else 0
        return a,f"SoccerStats247 O2.5={v:.0f}% ({a:+d})"
    if "OVER 1.5" in p and st.get("over15") is not None:
        v=st["over15"];a=4 if v>=75 else 2 if v>=65 else -3 if v<50 else 0
        return a,f"SoccerStats247 O1.5={v:.0f}% ({a:+d})"
    if p=="GG" and st.get("btts") is not None:
        v=st["btts"];a=4 if v>=60 else 2 if v>=52 else -3 if v<42 else 0
        return a,f"SoccerStats247 BTTS={v:.0f}% ({a:+d})"
    return 0,"SoccerStats247: nessun valore numerico applicabile"

def _forebet_adjustment(r,pick):
    st=r.get("forebet") or {}; p=(pick or "").upper().replace(",",".")
    if not st:return 0,"Forebet: dato non disponibile"
    fp=(st.get("pick") or "").upper().replace(",",".")
    # 1X2: use published probabilities where available; modest confirmation only.
    if p in ("1","X","2"):
        probs={"1":st.get("p1"),"X":st.get("px"),"2":st.get("p2")}
        v=probs.get(p)
        if fp==p and v is not None:
            a=5 if v>=50 else 3 if v>=40 else 2
            return a,f"Forebet {p}={v}% ({a:+d})"
        if fp in ("1","X","2") and fp!=p:return -3,f"Forebet indica {fp} (-3)"
    if "OVER 2.5" in p:
        if fp=="OVER 2.5":return 4,"Forebet conferma Over 2.5 (+4)"
        if st.get("predicted_goals") is not None and st["predicted_goals"]>=3:return 3,f"Forebet gol previsti={st['predicted_goals']} (+3)"
        if fp=="UNDER 2.5":return -3,"Forebet indica Under 2.5 (-3)"
    if "UNDER 2.5" in p:
        if fp=="UNDER 2.5":return 4,"Forebet conferma Under 2.5 (+4)"
        if st.get("predicted_goals") is not None and st["predicted_goals"]<=2:return 3,f"Forebet gol previsti={st['predicted_goals']} (+3)"
    if p=="GG" and fp=="GG":return 3,"Forebet conferma GG (+3)"
    return 0,"Forebet: nessuna conferma applicabile"

def final_for_row(r):
    methods=_method_candidates(r)
    if not methods:return None
    best=None
    for c in methods:
        supporters=[m for m in methods if _compatible(c["pick"],m["pick"])]
        # Prevent multiple market-derived methods from pretending to be independent.
        real=[m for m in supporters if not m["estimated"]]
        est=[m for m in supporters if m["estimated"]]
        sources=_source_support(r,c["pick"])
        conflicts=_conflicts(r,c["pick"])

        base=c["score"]
        real_bonus=min(10,max(0,len(real)-1)*4)
        est_bonus=min(5,len(est)*2)
        source_bonus=min(8,max(0,len(sources)-1)*3)
        conflict_penalty=min(12,len(conflicts)*4)

        afr_adjust,afr_reason=_afr_adjustment(r,c["pick"])
        fs_adjust,fs_reason=_footystats_adjustment(r,c["pick"])
        ss_adjust,ss_reason=_soccerstats247_adjustment(r,c["pick"])
        fb_adjust,fb_reason=_forebet_adjustment(r,c["pick"])
        final=base+real_bonus+est_bonus+source_bonus-conflict_penalty+afr_adjust+fs_adjust+ss_adjust+fb_adjust

        # Confidence discipline.
        # Pure market-estimate bets stay below FORTE unless a real Skianta signal supports them.
        has_real=bool(real)
        has_core=any(m["method"].startswith("BETPROFESSIONAL") for m in real)
        if not has_real: final=min(final,79)
        elif not has_core and all(m["estimated"] for m in supporters): final=min(final,79)
        if final>=90 and len(sources)<2 and len(real)<2:
            final=89
        final=max(0,min(95,round(final)))

        quality="REALE + STIMA" if real and est else ("REALE" if real else "STIMA MERCATO")
        key=(final,len(real),len(sources),base)
        item={
            "match":r.get("match",""),
            "market":_market_name(c["pick"],c["method"]),
            "pick":c["pick"],"score":final,
            "quality":quality,
            "methods":[m["method"] for m in supporters],
            "sources":sources,
            "conflicts":conflicts,
            "base":base,
            "afootballreport_adjust":afr_adjust,"afootballreport_reason":afr_reason,
             "footystats_adjust":fs_adjust,"footystats_reason":fs_reason,
            "soccerstats247_adjust":ss_adjust,"soccerstats247_reason":ss_reason,
            "forebet_adjust":fb_adjust,"forebet_reason":fb_reason,
            "reason":f"base {base} | metodi compatibili {len(supporters)} | fonti {len(sources)}"
                     + (f" | conflitti {len(conflicts)}" if conflicts else "")
                     + f" | {afr_reason} | {fs_reason} | {ss_reason} | {fb_reason}"
        }
        if best is None or key>best[0]:best=(key,item)
    return best[1] if best else None

def apply_final_bets(rows):
    for r in rows:
        r["final_bet"]=final_for_row(r)
    return rows

def top_final(rows,limit=10,min_score=60):
    bets=[r.get("final_bet") for r in rows if r.get("final_bet")]
    bets=[b for b in bets if b.get("score",0)>=min_score]
    bets=sorted(bets,key=lambda b:(b.get("score",0),len(b.get("sources",[])),len(b.get("methods",[]))),reverse=True)
    # one and only one bet per match
    out=[];seen=set()
    for b in bets:
        if b["match"] in seen:continue
        seen.add(b["match"]);out.append(b)
        if len(out)>=limit:break
    return out
