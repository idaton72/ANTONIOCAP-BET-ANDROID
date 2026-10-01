"""Automatic six-match history from football-data.org v4.

Optional provider: set FOOTBALL_DATA_TOKEN environment variable or
backend/config.json -> football_data_token. Only FINISHED matches are used.
No market-derived results are ever generated.
"""
import os, re, unicodedata, requests
from datetime import date, timedelta
from difflib import SequenceMatcher

BASE="https://api.football-data.org/v4"
COMPETITIONS={
    "premier league":"PL","england premier":"PL","championship":"ELC",
    "la liga":"PD","primera division spain":"PD","serie a":"SA",
    "bundesliga":"BL1","ligue 1":"FL1","eredivisie":"DED",
    "primeira liga":"PPL","liga portugal":"PPL","champions league":"CL",
    "uefa champions":"CL","world cup":"WC",
}

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

def _comp_code(league):
    n=_norm(league)
    best=(0,None)
    for label,code in COMPETITIONS.items():
        sc=_sim(n,label)
        if sc>best[0]:best=(sc,code)
    return best[1] if best[0]>=.62 else None

def _score(m):
    ft=((m.get("score") or {}).get("fullTime") or {})
    return ft.get("home"),ft.get("away")

def _perspective(matches, team_id):
    out=[]
    for m in sorted(matches,key=lambda x:x.get("utcDate", ""),reverse=True):
        if m.get("status")!="FINISHED":continue
        hg,ag=_score(m)
        if hg is None or ag is None:continue
        hid=(m.get("homeTeam") or {}).get("id"); aid=(m.get("awayTeam") or {}).get("id")
        if hid==team_id: out.append((int(hg),int(ag)))
        elif aid==team_id: out.append((int(ag),int(hg)))
        if len(out)>=6:break
    return out

class FootballDataHistoryCollector:
    def __init__(self,token=None):
        self.token=(token or os.getenv("FOOTBALL_DATA_TOKEN") or "").strip()
        self.s=requests.Session()
        if self.token:self.s.headers.update({"X-Auth-Token":self.token})
        self.team_cache={}; self.match_cache={}

    def _get(self,path,params=None):
        r=self.s.get(BASE+path,params=params,timeout=20)
        r.raise_for_status();return r.json()

    def _teams(self,code):
        if code not in self.team_cache:
            data=self._get(f"/competitions/{code}/teams")
            self.team_cache[code]=data.get("teams",[]) or []
        return self.team_cache[code]

    def _team(self,name,teams):
        best=(0,None)
        for t in teams:
            sc=max(_sim(name,t.get("name")),_sim(name,t.get("shortName")),_sim(name,t.get("tla")))
            if sc>best[0]:best=(sc,t)
        return best[1] if best[0]>=.72 else None

    def _last(self,tid):
        if tid not in self.match_cache:
            end=(date.today()-timedelta(days=1)).isoformat()
            data=self._get(f"/teams/{tid}/matches",{"status":"FINISHED","dateTo":end,"limit":12})
            self.match_cache[tid]=data.get("matches",[]) or []
        return self.match_cache[tid]

    def collect(self,fixtures):
        meta={"provider":"football-data.org","configured":bool(self.token),"site_reached":False,
              "matched":0,"complete":0,"requests_note":"solo risultati FINISHED; cache per esecuzione","error":""}
        if not self.token:
            meta["error"]="Token mancante: imposta FOOTBALL_DATA_TOKEN o football_data_token in config.json"
            return [],meta
        out=[]
        try:
            for f in fixtures:
                code=_comp_code(f.get("league"))
                if not code:continue
                teams=self._teams(code);meta["site_reached"]=True
                ht=self._team(f.get("home"),teams); at=self._team(f.get("away"),teams)
                if not ht or not at:continue
                meta["matched"]+=1
                hp=_perspective(self._last(ht["id"]),ht["id"])
                ap=_perspective(self._last(at["id"]),at["id"])
                if len(hp)<6 or len(ap)<6:continue
                hgf=[x[0] for x in hp]; hga=[x[1] for x in hp]
                agf=[x[0] for x in ap]; aga=[x[1] for x in ap]
                rec={"home":f.get("home"),"away":f.get("away"),"stats_source":"FOOTBALL-DATA.ORG AUTO",
                     "home_last10_for":";".join(map(str,hgf)),"home_last10_against":";".join(map(str,hga)),
                     "away_last10_for":";".join(map(str,agf)),"away_last10_against":";".join(map(str,aga)),
                     "home_gf_avg":round(sum(hgf)/6,3),"home_ga_avg":round(sum(hga)/6,3),
                     "away_gf_avg":round(sum(agf)/6,3),"away_ga_avg":round(sum(aga)/6,3)}
                out.append(rec);meta["complete"]+=1
        except Exception as e:
            meta["error"]=str(e)
        return out,meta
