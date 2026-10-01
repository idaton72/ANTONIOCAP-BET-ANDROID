def spread_state(a,b):
    if a is None or b is None:return "unknown"
    return "progression" if b<a else "regression" if b>a else "flat"
def total_state(a,b):
    if a is None or b is None:return "unknown"
    return "progression" if b>a else "regression" if b<a else "flat"
def price_state(a,b):
    if a is None or b is None:return "unknown"
    return "drop" if b<a else "rise" if b>a else "flat"

def evaluate(m):
    sp=spread_state(m.fav_spread_open,m.fav_spread_current)
    tot=total_state(m.total_open,m.total_current)
    ov=price_state(m.over_price_open,m.over_price_current)
    gg=price_state(getattr(m,"btts_gg_open",None),getattr(m,"btts_gg_current",None))
    score=0;reasons=[];strategies=[];signals=[]
    completeness=sum(v is not None for v in [m.fav_spread_open,m.fav_spread_current,m.total_open,m.total_current])/4
    if completeness==1:score+=20
    if tot=="progression":score+=22;signals.append("OVER 2,5");reasons.append(f"Total {m.total_open} → {m.total_current}")
    elif tot=="flat":score+=8
    if ov=="drop":score+=15;signals.append("OVER 2,5");reasons.append(f"Quota Over {m.over_price_open} → {m.over_price_current}")
    if gg=="drop":score+=22;signals.append("GG");reasons.append(f"Quota GG {m.btts_gg_open} → {m.btts_gg_current}")
    if sp=="progression":score+=12;reasons.append(f"AH {m.fav_spread_open} → {m.fav_spread_current}")
    elif sp=="regression":score+=5;reasons.append(f"AH regressione {m.fav_spread_open} → {m.fav_spread_current}")
    # BetProfessional combinations from real movements.
    if tot=="progression" and ov=="drop":
        strategies.append({"name":"Total in progressione + Over in calo","points":18});score+=18
    if gg=="drop" and (tot=="progression" or ov=="drop"):
        strategies.append({"name":"GG confermato dal mercato goal","points":15});score+=15
    if "GG" in signals and "OVER 2,5" in signals:
        pick="GG + OVER 2,5";score+=8
    elif "OVER 2,5" in signals:pick="OVER 2,5"
    elif "GG" in signals:pick="GG"
    else:pick="DA VERIFICARE"
    if completeness<1:
        score=min(score,59);reasons.append("DATI OPEN/CURRENT INCOMPLETI")
    return {"home":m.home,"away":m.away,"match":f"{m.home} – {m.away}","date":m.date,
      "kickoff":m.kickoff,"league":m.league,"source":m.source,"score":max(0,min(100,round(score))),
      "pick":pick,"strategies":strategies,"reasons":reasons,"completeness":round(completeness,2),"raw":m.dict()}
