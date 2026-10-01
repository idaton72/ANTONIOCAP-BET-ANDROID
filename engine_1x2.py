def _f(v):
    try: return float(v)
    except Exception: return None

def pct_drop(open_, current):
    op=_f(open_); cu=_f(current)
    if op is None or cu is None or op <= 0: return 0.0
    return (op-cu)/op*100.0

def _asian_ml(row, outcome):
    raw=row.get("raw",{}) or {}
    keys={
        "1":("ml_home_open","ml_home_current"),
        "X":("ml_draw_open","ml_draw_current"),
        "2":("ml_away_open","ml_away_current"),
    }
    a,b=keys[outcome]
    return raw.get(a),raw.get(b)

def _asian_base(drop):
    # AsianOdds alone can never exceed 72 points.
    if drop <= 0: return 0
    if drop < 1: return 8
    if drop < 2: return 16
    if drop < 3: return 25
    if drop < 4: return 34
    if drop < 5: return 43
    if drop < 7: return 52
    if drop < 10: return 60
    if drop < 15: return 66
    return 72


def reliability_label(score):
    if score >= 90: return "ECCELLENTE"
    if score >= 80: return "FORTE"
    if score >= 70: return "BUONO"
    if score >= 50: return "INTERESSANTE"
    return "NO BET"

def score_1x2(row):
    scores={"1":0,"X":0,"2":0}
    reasons={"1":[],"X":[],"2":[]}
    drops={}
    asian_active={"1":False,"X":False,"2":False}

    # A) AsianOdds OPEN -> CURRENT: primary signal.
    for outcome in ("1","X","2"):
        op,cu=_asian_ml(row,outcome)
        d=pct_drop(op,cu)
        drops[outcome]=d
        pts=_asian_base(d)
        if pts:
            asian_active[outcome]=True
            scores[outcome]+=pts
            reasons[outcome].append(f"AsianOdds {outcome}: {op} → {cu} ({d:.1f}% calo)")

    # B) Relative leadership bonus, modest.
    ordered=sorted(drops.items(),key=lambda x:x[1],reverse=True)
    if ordered and ordered[0][1] > 0:
        leader,top=ordered[0]
        second=ordered[1][1] if len(ordered)>1 else 0
        gap=top-second
        if gap >= 5:
            scores[leader]+=5
            reasons[leader].append("movimento nettamente dominante")
        elif gap >= 2:
            scores[leader]+=3
            reasons[leader].append("movimento prevalente")

    # C) Independent confirmations.
    # One secondary source = +12, second independent source = +10.
    confirmations={"1":set(),"X":set(),"2":set()}
    for m in row.get("source_matches",[]) or []:
        src=(m.get("source") or "").strip()
        if not src or src=="AsianOdds":
            continue
        for sig in m.get("signals",[]) or []:
            if not sig.startswith("1X2_DROP_"): continue
            tail=sig.split("1X2_DROP_",1)[1]
            for outcome in tail.split("/"):
                outcome=outcome.strip()
                if outcome in confirmations:
                    confirmations[outcome].add(src)

    for outcome in ("1","X","2"):
        conf=sorted(confirmations[outcome])
        if conf:
            scores[outcome]+=12
            reasons[outcome].append(f"{conf[0]} conferma {outcome}")
        if len(conf)>=2:
            scores[outcome]+=10
            reasons[outcome].append(f"{conf[1]} seconda conferma indipendente")

    # D) Current favourite price = small context bonus only.
    currents={}
    for outcome in ("1","X","2"):
        _,cu=_asian_ml(row,outcome)
        v=_f(cu)
        if v is not None: currents[outcome]=v
    if currents:
        fav=min(currents,key=currents.get)
        if asian_active[fav]:
            if currents[fav] <= 1.55:
                scores[fav]+=4
                reasons[fav].append("quota corrente molto bassa")
            elif currents[fav] <= 1.90:
                scores[fav]+=2
                reasons[fav].append("quota corrente da favorita")

    # E) Conflict penalty: if another outcome is also dropping strongly.
    for outcome in ("1","X","2"):
        rivals=[drops[o] for o in ("1","X","2") if o!=outcome]
        rival=max(rivals) if rivals else 0
        if drops[outcome] > 0 and rival >= 5:
            scores[outcome]-=8
            reasons[outcome].append("penalità: altro esito in forte calo")
        elif drops[outcome] > 0 and rival >= 3:
            scores[outcome]-=4
            reasons[outcome].append("penalità: segnale concorrente")

    scores={k:max(0,min(95,int(round(v)))) for k,v in scores.items()}
    pick=max(scores,key=scores.get)
    best=scores[pick]

    # F) Confidence discipline:
    # <50 NO BET. 90+ requires AsianOdds + two independent confirmations.
    nconf=len(confirmations[pick])
    if best >= 90 and not (asian_active[pick] and nconf>=2):
        best=min(best,89)
        scores[pick]=best
    if best >= 80 and not (asian_active[pick] and nconf>=1):
        best=min(best,79)
        scores[pick]=best

    if best < 50:
        pick="NO BET"
        best=0
        best_reasons=["segnale 1X2 insufficiente (<50)"]
    else:
        best_reasons=reasons[pick]

    return {
        "score_1":scores["1"], "score_x":scores["X"], "score_2":scores["2"],
        "pick_1x2":pick, "score_1x2":best, "reasons_1x2":best_reasons,
        "confirmations_1x2": sorted(confirmations[pick]) if pick in confirmations else [],
        "reliability_1x2": reliability_label(best)
    }

def enrich_1x2(rows):
    for r in rows:
        r.update(score_1x2(r))
    return rows
