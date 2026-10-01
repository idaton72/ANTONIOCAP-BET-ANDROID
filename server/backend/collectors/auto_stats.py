
import math

def _f(v):
    try:
        if v is None or v=="": return None
        x=float(str(v).replace(",","."))
        return x if x>0 else None
    except: return None

def _poisson_over25(lam):
    # P(total >= 3)
    return 1-math.exp(-lam)*(1+lam+(lam*lam)/2)

def _lambda_from_over25(p):
    p=max(.08,min(.92,p))
    lo,hi=.25,6.0
    for _ in range(45):
        mid=(lo+hi)/2
        if _poisson_over25(mid)<p:lo=mid
        else:hi=mid
    return (lo+hi)/2

def _novig_probs(qs):
    vals=[]
    for q in qs:
        q=_f(q)
        if not q:return None
        vals.append(1/q)
    s=sum(vals)
    return [v/s for v in vals] if s else None

def build_market_stats(rows):
    """
    Fallback automatico basato SOLO sui mercati gia raccolti.
    Non inventa statistiche storiche: source='STIMA MERCATO'.
    Serve per Poisson/Value quando non esistono dati storici importati.
    """
    out=[]
    for r in rows:
        raw=r.get("raw",{}) or {}
        q1=_f(raw.get("ml_home_current")); qx=_f(raw.get("ml_draw_current")); q2=_f(raw.get("ml_away_current"))
        qo=_f(raw.get("over_price_current")); qu=_f(raw.get("under_price_current"))
        probs=_novig_probs([q1,qx,q2]) if q1 and qx and q2 else None

        # Over 2.5 probability: prefer no-vig O/U; otherwise infer conservatively
        # from the Asian total line (2.5 is neutral, 3.0 higher, 2.0 lower).
        overp=None
        if qo and qu:
            ov=_novig_probs([qo,qu])
            if ov: overp=ov[0]
        line=_f(raw.get("total_current"))
        if overp is None and line:
            overp=max(.25,min(.75,.50+(line-2.5)*.16))
        if overp is None:
            continue

        total_lam=_lambda_from_over25(overp)
        if probs:
            # Strength split from no-vig home/away win probabilities.
            h,a=probs[0],probs[2]
            share=.5 if h+a<=0 else h/(h+a)
            # Compress split to avoid absurd lambdas.
            share=.30+.40*share
        else:
            share=.50
        lh=max(.15,total_lam*share); la=max(.15,total_lam*(1-share))

        # Poisson engine expects GF/GA averages. Equal-pair construction preserves
        # the derived lambdas exactly: (home_gf + away_ga)/2 = lh, etc.
        st={
            "home":r.get("home",""),"away":r.get("away",""),
            "home_gf_avg":round(lh,3),"away_ga_avg":round(lh,3),
            "away_gf_avg":round(la,3),"home_ga_avg":round(la,3),
            "home_over25_pct":round(overp*100,2),
            "away_over25_pct":round(overp*100,2),
            "over25_odds":qo,"under25_odds":qu,
            "stats_source":"STIMA MERCATO"
        }
        out.append(st)
    return out
