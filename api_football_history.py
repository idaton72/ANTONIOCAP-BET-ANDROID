"""API-Football v3 fallback for GOLBET six-match history.

Uses only completed fixtures (FT/AET/PEN). Configure API_FOOTBALL_KEY or
backend/config.json -> api_football_key. Persistent cache minimizes free-plan usage.
"""
import json, os, re, unicodedata, requests
from pathlib import Path
from difflib import SequenceMatcher

BASE="https://v3.football.api-sports.io"
CACHE_PATH=Path(__file__).with_name("api_football_cache.json")
FINISHED={"FT","AET","PEN"}

def _norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\b(fc|cf|sc|afc|fk|ac|club|calcio)\b"," ",s)
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

def _sim(a,b):
    a,b=_norm(a),_norm(b)
    if not a or not b:return 0
    if a==b:return 1
    if a in b or b in a:return .94
    return SequenceMatcher(None,a,b).ratio()

def _load_cache():
    try:return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except:return {"teams":{},"history":{}}

def _save_cache(c):
    try:CACHE_PATH.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding="utf-8")
    except:pass

class ApiFootballHistoryCollector:
    def __init__(self,key=None,max_requests=40):
        self.key=(key or os.getenv("API_FOOTBALL_KEY") or "").strip()
        self.max_requests=max(1,int(max_requests or 40)); self.used=0
        self.remaining=None; self.s=requests.Session(); self.cache=_load_cache()
        if self.key:self.s.headers.update({"x-apisports-key":self.key})

    def _get(self,path,params=None):
        if self.used>=self.max_requests: raise RuntimeError("Limite richieste API-Football per esecuzione raggiunto")
        r=self.s.get(BASE+path,params=params,timeout=20); self.used+=1
        try:self.remaining=int(r.headers.get("x-ratelimit-requests-remaining"))
        except:pass
        r.raise_for_status(); data=r.json()
        if data.get("errors"):
            raise RuntimeError("API-Football: "+str(data.get("errors")))
        return data.get("response",[]) or []

    def _team_id(self,name):
        k=_norm(name)
        cached=self.cache.get("teams",{}).get(k)
        if cached:return cached.get("id")
        results=self._get("/teams",{"search":name})
        best=(0,None,None)
        for x in results:
            t=x.get("team") or {}; sc=_sim(name,t.get("name"))
            if sc>best[0]:best=(sc,t.get("id"),t.get("name"))
        if best[0] < .72 or not best[1]:return None
        self.cache.setdefault("teams",{})[k]={"id":best[1],"name":best[2]}; _save_cache(self.cache)
        return best[1]

    def _last6(self,tid):
        ck=str(tid)
        cached=self.cache.get("history",{}).get(ck)
        if cached and len(cached)>=6:return [tuple(x) for x in cached[:6]]
        rows=self._get("/fixtures",{"team":tid,"last":6})
        out=[]
        for x in rows:
            st=((x.get("fixture") or {}).get("status") or {}).get("short")
            if st not in FINISHED:continue
            goals=x.get("goals") or {}; hg=goals.get("home"); ag=goals.get("away")
            teams=x.get("teams") or {}; hid=((teams.get("home") or {}).get("id")); aid=((teams.get("away") or {}).get("id"))
            if hg is None or ag is None:continue
            if hid==tid:out.append((int(hg),int(ag)))
            elif aid==tid:out.append((int(ag),int(hg)))
        if len(out)>=6:
            self.cache.setdefault("history",{})[ck]=out[:6]; _save_cache(self.cache)
        return out[:6]

    def collect(self,fixtures):
        meta={"provider":"API-Football","configured":bool(self.key),"site_reached":False,"matched":0,
              "complete":0,"requests":0,"remaining":None,"error":""}
        if not self.key:
            meta["error"]="API key mancante: imposta API_FOOTBALL_KEY o api_football_key in config.json"
            return [],meta
        out=[]
        try:
            for f in fixtures:
                # Stop early if quota is nearly exhausted when the provider reports it.
                if self.remaining is not None and self.remaining<=5:break
                ht=self._team_id(f.get("home")); at=self._team_id(f.get("away"))
                if not ht or not at:continue
                meta["site_reached"]=True; meta["matched"]+=1
                hp=self._last6(ht); ap=self._last6(at)
                if len(hp)<6 or len(ap)<6:continue
                hgf=[x[0] for x in hp]; hga=[x[1] for x in hp]; agf=[x[0] for x in ap]; aga=[x[1] for x in ap]
                out.append({"home":f.get("home"),"away":f.get("away"),"stats_source":"API-FOOTBALL AUTO",
                    "home_last10_for":";".join(map(str,hgf)),"home_last10_against":";".join(map(str,hga)),
                    "away_last10_for":";".join(map(str,agf)),"away_last10_against":";".join(map(str,aga)),
                    "home_gf_avg":round(sum(hgf)/6,3),"home_ga_avg":round(sum(hga)/6,3),
                    "away_gf_avg":round(sum(agf)/6,3),"away_ga_avg":round(sum(aga)/6,3)})
                meta["complete"]+=1
        except Exception as e:meta["error"]=str(e)
        meta["requests"]=self.used; meta["remaining"]=self.remaining
        _save_cache(self.cache)
        return out,meta
