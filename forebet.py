import re, unicodedata, requests, json, datetime
from pathlib import Path
from bs4 import BeautifulSoup
from rapidfuzz.fuzz import ratio

URLS=[
 "https://www.forebet.com/it/pronostici-di-calcio-per-oggi",
 "https://www.forebet.com/it/pronostici-calcio-over-under",
 "https://www.forebet.com/it/pronostici-calcio-btts",
]
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"}

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\b(fc|cf|sc|afc|fk|ac|club|calcio)\b"," ",s)
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

def pct(s):
    m=re.search(r"(\d{1,3})\s*%",str(s or ""))
    return int(m.group(1)) if m else None

def _pick(text):
    t=" "+str(text or "").upper().replace(",",".")+" "
    # Explicit result/prediction tokens only.
    m=re.search(r"(?:PRONOSTICO|PREDICTION|TIP)\s*[:\-]?\s*(1|X|2)\b",t)
    if m:return m.group(1)
    if re.search(r"\bOVER\s*2\.5\b",t):return "OVER 2.5"
    if re.search(r"\bUNDER\s*2\.5\b",t):return "UNDER 2.5"
    if re.search(r"\b(BTTS|GG|GOAL\s*/?\s*GOAL)\b",t):return "GG"
    if re.search(r"\b(NO\s*GOAL|NG)\b",t):return "NG"
    return None

def _parse_html(html):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    # Forebet markup can vary; use visible row/card containers and keep only records
    # with at least two plausible team labels.
    candidates=soup.select("tr, .rcnt, .predict, .prediction, [class*='forecast'], [class*='match']")
    seen=set()
    for el in candidates:
        text=" ".join(el.get_text(" ",strip=True).split())
        if len(text)<8:continue
        links=[" ".join(a.get_text(" ",strip=True).split()) for a in el.select("a") if a.get_text(" ",strip=True)]
        teams=[]
        for x in links:
            nx=norm(x)
            if 2<=len(nx)<=45 and not any(w in nx for w in ("pronost","classifica","risultat","statistic","league","campionat")):
                if x not in teams:teams.append(x)
        if len(teams)<2:continue
        home,away=teams[-2],teams[-1]
        key=(norm(home),norm(away),text[:100])
        if key in seen:continue
        seen.add(key)
        percentages=[int(x) for x in re.findall(r"(\d{1,3})\s*%",text) if 0<=int(x)<=100]
        rec={"home":home,"away":away,"text":text[:1200],"pick":_pick(text)}
        if len(percentages)>=3:
            rec.update({"p1":percentages[0],"px":percentages[1],"p2":percentages[2]})
            if not rec["pick"]:
                rec["pick"]=("1","X","2")[max(range(3),key=lambda i:percentages[i])]
        # predicted score / total-goal clue, when visibly present
        sm=re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b",text)
        if sm:
            a,b=map(int,sm.groups())
            if a<=15 and b<=15:rec["predicted_goals"]=a+b;rec["predicted_score"]=f"{a}-{b}"
        out.append(rec)
    return out

CACHE_DIR=Path.home()/"Documents"/"ANTONIOCAP.BET"
CACHE_FILE=CACHE_DIR/"forebet_public_cache.json"

def import_public_files(paths):
    """Importa pagine Forebet salvate normalmente dal browser (HTML/HTM).
    Nessun accesso automatico al sito e nessun aggiramento di protezioni.
    """
    rows=[]; files=0
    for raw in paths:
        path=Path(raw)
        try:
            html=path.read_text(encoding="utf-8",errors="ignore")
            parsed=_parse_html(html)
            rows.extend(parsed); files+=1
        except Exception:
            continue
    # deduplica conservativa
    uniq={}
    for x in rows:
        k=(norm(x.get("home")),norm(x.get("away")))
        if all(k): uniq[k]=x
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    payload={"created":datetime.datetime.now().isoformat(timespec="seconds"),"files":files,"rows":list(uniq.values())}
    CACHE_FILE.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return len(uniq),str(CACHE_FILE)

def _load_cache():
    try:
        obj=json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return obj.get("rows",[]) or [],obj.get("created","")
    except Exception:
        return [],""

class ForebetCollector:
    def collect(self,fixtures):
        meta={"site_reached":False,"pages_read":0,"rows_read":0,"matched":0,"used":0,"errors":[]}
        rows,created=_load_cache()
        meta["rows_read"]=len(rows); meta["cache_created"]=created
        meta["local_public_import"]=bool(rows)
        data={}
        for f in fixtures:
            h,a=norm(f.get("home")),norm(f.get("away")); best=None;bs=0
            for x in rows:
                xh,xa=norm(x.get("home")),norm(x.get("away"))
                sc=(ratio(h,xh)+ratio(a,xa))/200
                rev=(ratio(h,xa)+ratio(a,xh))/200
                if rev>sc:sc=rev
                if sc>bs:bs=sc;best=x
            if best and bs>=0.72:
                data[(h,a)]={**best,"similarity":round(bs,3)}
                meta["matched"]+=1;meta["used"]+=1
        meta["site_reached"]=bool(rows)
        meta["error"]=""
        meta["restricted_detail"]=""
        return data,meta

def attach(rows,data):
    for r in rows:r["forebet"]=data.get((norm(r.get("home")),norm(r.get("away"))))
    return rows
