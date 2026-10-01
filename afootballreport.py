
import re, unicodedata, requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
URLS={
 "1X2":"https://afootballreport.com/it/pronostici/1X2-pronostici-di-calcio/",
 "OU":"https://afootballreport.com/it/pronostici/under-over-goal/",
 "HT":"https://afootballreport.com/it/pronostici/primo-tempo-under-over-goals/",
 "BTTS":"https://afootballreport.com/it/pronostici/entrambre-squadre-segnano/",
}
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\b(fc|cf|sc|afc|fk|ac|club|calcio)\b"," ",s)
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())
def hit(team,text):
    a,b=norm(team),norm(text)
    if not a or not b:return 0
    if a in b:return 1.0
    toks=[x for x in a.split() if len(x)>=3]
    return sum(x in b.split() for x in toks)/(len(toks) or 1)
def row_blocks(html):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    # Actual public pages expose "squadra di casa - squadra in trasferta | Suggerimento | logica".
    for node in soup.select("tr, .table-row, .prediction-row, .match-row, li, table tbody tr"):
        txt=" | ".join(node.stripped_strings)
        if len(txt)>15: out.append(txt)
    # Fallback for sites whose visual rows are div-based.
    text=soup.get_text("\n",strip=True)
    lines=[" ".join(x.split()) for x in text.splitlines() if x.strip()]
    for i in range(len(lines)):
        w=" | ".join(lines[i:i+5])
        if re.search(r"\d{2}/\d{2}\s+\d{2}:\d{2}",w): out.append(w)
    return out
def parse_pick(block,market):
    if market=="BTTS" and re.search(r"\bBtts\b|Entrambe le Squadre",block,re.I): return "GG"
    if market in ("OU","HT"):
        m=re.search(r"\b(Over|Under)\s*(0[.,]5|1[.,]5|2[.,]5|3[.,]5)\b",block,re.I)
        return (m.group(1).upper()+" "+m.group(2).replace(",",".")) if m else None
    if market=="1X2":
        # Suggestion column usually contains 1/X/2. Prefer explicit percentage label.
        m=re.search(r"(?:Suggerimento|Tip|Pronostico)?\s*\|?\s*\b(1|X|2)\b(?=\s*\||\s*$)",block,re.I)
        if m:return m.group(1).upper()
        ps={k.upper():float(v.replace(",",".")) for k,v in re.findall(r"\b([1X2])\s+(\d+(?:[.,]\d+)?)%",block,re.I)}
        if ps:return max(ps,key=ps.get)
    return None

class AFootballReportCollector:
    def collect(self,fixtures):
        sess=requests.Session();sess.headers.update(HEADERS)
        pages={}; meta={"site_reached":False,"pages_read":0,"rows_read":0,"matched":0,"used":0}
        for market,url in URLS.items():
            try:
                r=sess.get(url,timeout=25);r.raise_for_status();meta["site_reached"]=True
                blocks=row_blocks(r.text);pages[market]=blocks;meta["pages_read"]+=1;meta["rows_read"]+=len(blocks)
            except Exception as e:
                pages[market]=[]
                meta.setdefault("errors",[]).append(f"{market}: {e}")
        bymatch={}
        for f in fixtures:
            recs=[]
            for market,blocks in pages.items():
                best=None
                for b in blocks:
                    sc=(hit(f.get("home"),b)+hit(f.get("away"),b))/2
                    if sc>=.70:
                        pick=parse_pick(b,market)
                        if pick and (best is None or sc>best[0]): best=(sc,pick,b)
                if best:
                    b=best[2]
                    r={"market":market,"pick":best[1],"match_score":round(best[0],3),
                       "logic":b[:500],"source":"AFootballReport"}
                    ps={k.upper():float(v.replace(",",".")) for k,v in re.findall(r"\b([1X2])\s+(\d+(?:[.,]\d+)?)%",b,re.I)}
                    r.update(p1=ps.get("1"),px=ps.get("X"),p2=ps.get("2"))
                    recs.append(r)
            if recs:
                bymatch[(norm(f.get("home")),norm(f.get("away")))]=recs;meta["matched"]+=1;meta["used"]+=len(recs)
        meta["error"]="; ".join(meta.get("errors",[]))
        return bymatch,meta

def attach(rows,data):
    for r in rows:
        r["afootballreport"]=data.get((norm(r.get("home")),norm(r.get("away"))),[])
    return rows
