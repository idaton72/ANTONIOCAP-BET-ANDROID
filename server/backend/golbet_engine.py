"""GOLBET v1.0 engine, ported from the user-provided workbook/PDF.

Faithful rules:
- uses the latest six matches only;
- G HOME=(home GF + away GA)/12; G AWAY=(away GF + home GA)/12;
- green signals are values above the day's average among matches with real historical data;
- G TOTAL green -> OVER 1.5 / optional OVER 2.5; both team propensities green -> GG;
- rating = home goal difference - away goal difference; positive -> 1X (risky 1), negative -> X2 (risky 2);
- form=(wins*3)/18; anger=(18-points)/18.
No market-derived proxy is used: if six-match history is unavailable, GOLBET stays unavailable.
"""
from .engine_multimethod import get_stats_for_match


def _ints(v):
    if v is None: return []
    import re
    out=[]
    for x in re.split(r"[;|,\s]+",str(v).strip()):
        if not x: continue
        try: out.append(int(float(x)))
        except Exception: pass
    return out


def _six(st,prefix):
    gf=_ints(st.get(prefix+"_last10_for"))[:6]
    ga=_ints(st.get(prefix+"_last10_against"))[:6]
    if len(gf)<6 or len(ga)<6: return None
    wins=draws=points=0
    for a,b in zip(gf,ga):
        if a>b: wins+=1; points+=3
        elif a==b: draws+=1; points+=1
    return {"gf":sum(gf),"ga":sum(ga),"gd":sum(gf)-sum(ga),"wins":wins,"draws":draws,
            "points":points,"form":(wins*3)/18,"anger":(18-points)/18}


def attach_golbet(rows):
    prepared=[]
    for r in rows:
        st=get_stats_for_match(r.get("home"),r.get("away"))
        # Never use automatic market estimates for this legacy statistical method.
        if not st or st.get("stats_source")=="STIMA MERCATO":
            prepared.append((r,None)); continue
        h=_six(st,"home"); a=_six(st,"away")
        if not h or not a:
            prepared.append((r,None)); continue
        gh=(h["gf"]+a["ga"])/12
        ga=(a["gf"]+h["ga"])/12
        prepared.append((r,{"home":h,"away":a,"g_home":gh,"g_away":ga,"g_total":gh+ga,
                            "rating":h["gd"]-a["gd"]}))

    vals=[d for _,d in prepared if d]
    avgs={}
    if vals:
        for k in ("g_home","g_away","g_total"):
            avgs[k]=sum(d[k] for d in vals)/len(vals)
        avgs["form_home"]=sum(d["home"]["form"] for d in vals)/len(vals)
        avgs["form_away"]=sum(d["away"]["form"] for d in vals)/len(vals)
        avgs["anger_home"]=sum(d["home"]["anger"] for d in vals)/len(vals)
        avgs["anger_away"]=sum(d["away"]["anger"] for d in vals)/len(vals)

    for r,d in prepared:
        r["golbet_available"]=bool(d)
        if not d: continue
        gh_green=d["g_home"]>avgs["g_home"]
        ga_green=d["g_away"]>avgs["g_away"]
        gt_green=d["g_total"]>avgs["g_total"]
        signals=[]
        if gh_green: signals.append("HOME SEGNA")
        if ga_green: signals.append("AWAY SEGNA")
        if gt_green: signals.extend(["OVER 1,5","OVER 2,5 (RISCHIO)"])
        if gh_green and ga_green: signals.append("GG")
        rating=d["rating"]
        dc="1X" if rating>0 else "X2" if rating<0 else "12"
        risky="1" if rating>0 else "2" if rating<0 else None
        r["golbet_g_home"]=round(d["g_home"],3); r["golbet_g_away"]=round(d["g_away"],3)
        r["golbet_g_total"]=round(d["g_total"],3); r["golbet_rating"]=rating
        r["golbet_dc"]=dc; r["golbet_risky_1x2"]=risky; r["golbet_signals"]=signals
        r["golbet_form_home"]=round(d["home"]["form"],3); r["golbet_form_away"]=round(d["away"]["form"],3)
        r["golbet_anger_home"]=round(d["home"]["anger"],3); r["golbet_anger_away"]=round(d["away"]["anger"],3)
        r["golbet_green"]={"g_home":gh_green,"g_away":ga_green,"g_total":gt_green,
            "form_home":d["home"]["form"]>avgs["form_home"],"form_away":d["away"]["form"]>avgs["form_away"],
            "anger_home":d["home"]["anger"]>avgs["anger_home"],"anger_away":d["away"]["anger"]>avgs["anger_away"]}
        r["golbet_day_avg"]={k:round(v,3) for k,v in avgs.items()}
    return rows
