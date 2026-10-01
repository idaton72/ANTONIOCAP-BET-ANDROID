import json, re, unicodedata, csv
from pathlib import Path
from datetime import datetime
import requests
from rapidfuzz.fuzz import ratio

DATA_DIR=Path.home()/"Documents"/"ANTONIOCAP.BET"
DATA_DIR.mkdir(parents=True,exist_ok=True)
DB=DATA_DIR/"performance_history.json"

def _load():
    try:return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:return []
def _save(rows):DB.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
def _norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()
def _teams(match):
    p=re.split(r"\\s+-\\s+",str(match),maxsplit=1);return (p+[""])[:2]

def snapshot(day,bets):
    rows=_load();keys={(x.get("date"),x.get("match"),x.get("market"),x.get("pick")) for x in rows};n=0
    for b in bets:
        k=(day,b.get("match"),b.get("market"),b.get("pick"))
        if k in keys:continue
        rows.append({"date":day,"match":b.get("match",""),"market":b.get("market",""),"pick":b.get("pick",""),
        "score":int(b.get("score",0) or 0),"quality":b.get("quality",""),"sources":b.get("sources",[]),
        "methods":b.get("methods",[]),"home_goals":None,"away_goals":None,"status":"PENDING","result_source":"","checked_at":""})
        n+=1
    _save(rows);return n

def _grade(x,h,a):
    p=str(x.get("pick","")).upper().replace(",",".").strip()
    if p=="1":ok=h>a
    elif p=="X":ok=h==a
    elif p=="2":ok=a>h
    elif p=="GG":ok=h>0 and a>0
    elif p in ("NG","NO GOAL"):ok=h==0 or a==0
    elif "GG + OVER 2.5" in p:ok=h>0 and a>0 and h+a>2.5
    elif "OVER 2.5" in p:ok=h+a>2.5
    elif "UNDER 2.5" in p:ok=h+a<2.5
    elif "OVER 1.5" in p:ok=h+a>1.5
    elif "UNDER 3.5" in p:ok=h+a<3.5
    else:return "VOID"
    return "WIN" if ok else "LOSS"

def update_public_results():
    rows=_load();dates=sorted({x["date"] for x in rows if x.get("status")=="PENDING"});matched=0;errors=[]
    for day in dates[-7:]:
        try:
            u=f"https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d={day}&s=Soccer"
            r=requests.get(u,timeout=15);r.raise_for_status();events=(r.json() or {}).get("events") or []
        except Exception as e:errors.append(f"{day}: {e}");continue
        for x in rows:
            if x.get("date")!=day or x.get("status")!="PENDING":continue
            ph,pa=_teams(x.get("match",""));best=None
            for ev in events:
                sc=(ratio(_norm(ph),_norm(ev.get("strHomeTeam","")))+ratio(_norm(pa),_norm(ev.get("strAwayTeam",""))))/2
                if best is None or sc>best[0]:best=(sc,ev)
            if not best or best[0]<72:continue
            ev=best[1]
            try:h=int(ev.get("intHomeScore"));a=int(ev.get("intAwayScore"))
            except Exception:continue
            x["home_goals"]=h;x["away_goals"]=a;x["status"]=_grade(x,h,a);x["result_source"]="TheSportsDB"
            x["checked_at"]=datetime.now().isoformat(timespec="seconds");matched+=1
    _save(rows);return matched,errors

def import_results_csv(path):
    rows=_load();n=0
    with open(path,"r",encoding="utf-8-sig",newline="") as f:
        for rec in csv.DictReader(f):
            day=(rec.get("date") or "").strip();match=(rec.get("match") or "").strip()
            try:h=int(rec.get("home_goals"));a=int(rec.get("away_goals"))
            except Exception:continue
            for x in rows:
                if x.get("date")==day and ratio(_norm(x.get("match")),_norm(match))>=82:
                    x["home_goals"]=h;x["away_goals"]=a;x["status"]=_grade(x,h,a);x["result_source"]="CSV"
                    x["checked_at"]=datetime.now().isoformat(timespec="seconds");n+=1
    _save(rows);return n

def summary():
    rows=_load();done=[x for x in rows if x.get("status") in ("WIN","LOSS")]
    wins=sum(x["status"]=="WIN" for x in done);losses=len(done)-wins;pct=wins/len(done)*100 if done else 0
    bands={};markets={}
    for x in done:
        s=int(x.get("score",0));b="90+" if s>=90 else "85-89" if s>=85 else "80-84" if s>=80 else "70-79" if s>=70 else "<70"
        d=bands.setdefault(b,[0,0]);d[0]+=1;d[1]+=x["status"]=="WIN"
        d=markets.setdefault(x.get("market","?"),[0,0]);d[0]+=1;d[1]+=x["status"]=="WIN"
    return rows,{"done":len(done),"wins":wins,"losses":losses,"pct":pct,"pending":sum(x.get("status")=="PENDING" for x in rows),"bands":bands,"markets":markets}
