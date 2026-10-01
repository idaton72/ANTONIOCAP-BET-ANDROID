from pathlib import Path

import re, unicodedata, requests, json, datetime
from bs4 import BeautifulSoup
PAGES={
 "over25":"https://footystats.org/stats/over25-goals",
 "over15":"https://footystats.org/stats/over15-goals",
 "btts":"https://footystats.org/stats/btts-stats",
 "half":"https://footystats.org/stats/1st-2nd-half-goals",
}
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}
def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\b(fc|cf|sc|afc|fk|ac|club|calcio)\b"," ",s)
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())
def parse_percent_table(html,kind):
    soup=BeautifulSoup(html,"html.parser");out={};rows=0
    for tr in soup.find_all("tr"):
        cells=[" ".join(x.stripped_strings) for x in tr.find_all(["td","th"])]
        if len(cells)<3:continue
        joined=" | ".join(cells)
        pms=re.findall(r"(\d+(?:[.,]\d+)?)\s*%",joined)
        if not pms:continue
        team=None
        # Prefer linked team name; it avoids selecting country/league/rank labels.
        a=tr.find("a")
        if a:
            z=" ".join(a.stripped_strings)
            if z and len(z)<=100:team=z
        if not team:
            for c in cells:
                z=c.strip()
                if z and not re.fullmatch(r"\d+",z) and "%" not in z and "match" not in z.lower() and "over" not in z.lower():
                    if len(z)<=100:team=z;break
        if team:
            out[norm(team)]={"team":team,kind:float(pms[-1].replace(",","."))};rows+=1
    return out,rows

def parse_percent_text(html,kind):
    soup=BeautifulSoup(html,"html.parser")
    text=soup.get_text("\n",strip=True)
    lines=[" ".join(x.split()) for x in text.splitlines() if x.strip()]
    out={}; rows=0
    # Rendered public table is Team | Over X count | % | Next Match | Odds.
    for i,line in enumerate(lines):
        if not re.fullmatch(r"\d+(?:[.,]\d+)?%", line): continue
        pct=float(line[:-1].replace(",","."))
        # search backward for a plausible team label, skipping counts/headings
        team=None
        for j in range(i-1,max(-1,i-7),-1):
            z=lines[j]
            if (2<=len(z)<=100 and not re.fullmatch(r"[\d\s/.,%-]+",z)
                and not re.search(r"over|under|match|odds|team|stats|goals",z,re.I)):
                team=z;break
        if team:
            out[norm(team)]={"team":team,kind:pct}; rows+=1
    return out,rows

def parse_half(html):
    soup=BeautifulSoup(html,"html.parser");out={};rows=0
    for tr in soup.find_all("tr"):
        cells=[" ".join(x.stripped_strings) for x in tr.find_all(["td","th"])]
        if len(cells)<3:continue
        nums=[]
        for c in cells:
            try:
                v=float(c.replace(",",".").strip())
                if 0<=v<=10: nums.append(v)
            except:pass
        team=next((c for c in cells if c and not re.fullmatch(r"\d+",c) and len(c)<80 and not re.search(r"match",c,re.I)),None)
        if team and nums:
            out[norm(team)]={"team":team,"avg_fh_goals":nums[-1]};rows+=1
    return out,rows
def find_team(team,table):
    n=norm(team)
    if n in table:return table[n]
    toks=[x for x in n.split() if len(x)>=4]
    best=None
    for k,v in table.items():
        score=sum(t in k.split() for t in toks)/(len(toks) or 1)
        if score>=.75 and (best is None or score>best[0]):best=(score,v)
    return best[1] if best else None

class FootyStatsCollector:
    def collect(self,fixtures):
        s=requests.Session();s.headers.update(HEADERS)
        tables={};meta={"site_reached":False,"pages_read":0,"rows_read":0,"matched":0,"used":0}
        debug_pages=[]
        for kind,url in PAGES.items():
            try:
                r=s.get(url,timeout=25);r.raise_for_status();meta["site_reached"]=True;meta["pages_read"]+=1
                if kind=="half":t,n=parse_half(r.text)
                else:
                    t,n=parse_percent_table(r.text,kind)
                    if n==0:t,n=parse_percent_text(r.text,kind)
                tables[kind]=t;meta["rows_read"]+=n
                soup=BeautifulSoup(r.text,"html.parser")
                debug_pages.append({"kind":kind,"url":url,"status":r.status_code,
                    "final_url":r.url,"title":soup.title.get_text(" ",strip=True) if soup.title else "",
                    "html_length":len(r.text),"parsed_rows":n,
                    "team_sample":[v.get("team") for v in list(t.values())[:15]],
                    "text_sample":soup.get_text(" ",strip=True)[:1200]})
            except Exception as e:
                tables[kind]={};meta.setdefault("errors",[]).append(f"{kind}: {e}")
        out={}
        for f in fixtures:
            h,a=f.get("home",""),f.get("away","")
            rec={"source":"FootyStats","home_team":h,"away_team":a};vals=0
            for kind in ("over25","over15","btts","half"):
                hv=find_team(h,tables.get(kind,{}));av=find_team(a,tables.get(kind,{}))
                if kind=="half":
                    vs=[x.get("avg_fh_goals") for x in (hv,av) if x and x.get("avg_fh_goals") is not None]
                    if vs:rec["avg_fh_goals"]=round(sum(vs)/len(vs),2);vals+=1
                else:
                    vs=[x.get(kind) for x in (hv,av) if x and x.get(kind) is not None]
                    if vs:rec[kind]=round(sum(vs)/len(vs),1);vals+=1
            if vals:
                rec["values_found"]=vals
                out[(norm(h),norm(a))]=rec;meta["matched"]+=1;meta["used"]+=vals
        meta["stats"]=meta["matched"];meta["error"]="; ".join(meta.get("errors",[]))
        try:
            dbg={"timestamp":datetime.datetime.now().isoformat(),"meta":meta,"pages":debug_pages,
                 "fixture_sample":[{"league":x.get("league"),"home":x.get("home"),"away":x.get("away")} for x in fixtures[:10]]}
            debug_dir=Path.home()/"Documents"/"ANTONIOCAP.BET"/"DEBUG"
            debug_dir.mkdir(parents=True,exist_ok=True)
            with open(debug_dir/"DEBUG_FOOTYSTATS_371.json","w",encoding="utf-8") as fh:
                json.dump(dbg,fh,ensure_ascii=False,indent=2)
        except: pass
        return out,meta
def attach(rows,data):
    for r in rows:r["footystats"]=data.get((norm(r.get("home")),norm(r.get("away"))))
    return rows
