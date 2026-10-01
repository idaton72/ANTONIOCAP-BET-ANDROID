"""NOWGOALBET signal ported from the uploaded V.01.xlsm Foglio2 rules.

The legacy workbook compared opening vs later 1X2 odds and bookmaker payout.
This module reproduces the four decision branches without depending on Excel or
on the obsolete NowGoal web scraper.  It uses the OPEN/CURRENT 1X2 prices that
ANTONIOCAP.BET already receives from AsianOdds.
"""

def _f(v):
    try:
        x=float(v)
        return x if x > 0 else None
    except Exception:
        return None


def _payout(odds):
    vals=[_f(x) for x in odds]
    if any(x is None for x in vals): return None
    s=sum(1.0/x for x in vals)
    return 1.0/s if s else None


def _eq(a,b,eps=1e-9):
    return a is not None and b is not None and abs(a-b)<=eps


def signal_from_odds(open_odds,current_odds):
    op=[_f(x) for x in open_odds]; cu=[_f(x) for x in current_odds]
    if any(x is None for x in op+cu):
        return {"available":False,"signal":None,"direction":None,"rule":None}

    po=_payout(op); pc=_payout(cu)
    # Excel Foglio2: O=200-open_payout*100, P=200-current_payout*100;
    # Q="GIU" when O>P, "SU" when P>O.
    direction="GIU" if po>pc else ("SU" if pc>po else "")
    mn_o,mn_c=min(op),min(cu); mx_o,mx_c=max(op),max(cu)
    sig=None; rule=None

    # Exact precedence from Foglio2 S: U -> W -> Y -> AA.
    if direction=="SU" and mn_o>mn_c:
        if _eq(mn_c,cu[0]): sig="1"
        elif _eq(mn_c,cu[2]): sig="2"
        if sig: rule="SU_MIN_CURRENT"

    if sig is None and direction=="SU" and (mx_o-mx_c)>=0.40:
        if _eq(mx_o,op[0]): sig="1X"
        elif _eq(mx_o,op[2]): sig="X2"
        if sig: rule="SU_MAX_DROP_040"

    delta_max=mx_o-mx_c
    if sig is None and direction=="GIU" and 0.15<=delta_max<=0.25:
        sig=("1","X","2")[op.index(mn_o)]
        rule="GIU_MAX_DROP_015_025"

    delta_min=mn_o-mn_c
    if sig is None and direction=="GIU" and 0.15<=delta_min<=0.25:
        sig=("1","X","2")[cu.index(mn_c)]
        rule="GIU_MIN_DROP_015_025"

    return {
        "available":True,"signal":sig,"direction":direction,"rule":rule,
        "open_odds":op,"current_odds":cu,
        "open_payout":round(po,6),"current_payout":round(pc,6),
        "delta_min":round(delta_min,4),"delta_max":round(delta_max,4),
    }


def attach_nowgoalbet(rows):
    for r in rows:
        raw=r.get("raw",{}) or {}
        op=[raw.get("ml_home_open"),raw.get("ml_draw_open"),raw.get("ml_away_open")]
        cu=[raw.get("ml_home_current"),raw.get("ml_draw_current"),raw.get("ml_away_current")]
        d=signal_from_odds(op,cu)
        r["nowgoalbet_available"]=d["available"]
        r["nowgoalbet_signal"]=d.get("signal")
        r["nowgoalbet_direction"]=d.get("direction")
        r["nowgoalbet_rule"]=d.get("rule")
        r["nowgoalbet_diag"]=d
    return rows
