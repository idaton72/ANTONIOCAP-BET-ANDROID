"""Betshoot Dropping Odds collector for ANTONIOCAP.BET.
Public/free rows only. No login/paywall bypass. Extracts opening/current prices for
1/X/2, O2.5, U2.5 and BTTS and turns genuine price decreases into signals.
"""
import re, requests
from bs4 import BeautifulSoup
from .multisource import match_score

URL="https://www.betshoot.com/dropping-odds/"
HEADERS={"User-Agent":"Mozilla/5.0 (ANTONIOCAP.BET/3.8.6; Android bridge)"}
PAIR_RE=re.compile(r"^\s*(.+?)\s+[-–—]\s+(.+?)\s*$")
ODD_RE=re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2})(?!\d)")


def _signals(vals):
    # Expected public order: 1(open,current), X, 2, O2.5, U2.5, BTTS.
    names=("1","X","2","OVER25","UNDER25","BTTS")
    out=[]
    if len(vals) < 12: return out
    for i,name in enumerate(names):
        op,cur=vals[i*2],vals[i*2+1]
        if op>0 and cur < op:
            pct=round((op-cur)/op*100,1)
            out.append(f"BETSHOOT_DROP_{name}_{pct}%")
    return out


def parse_html(html):
    soup=BeautifulSoup(html,"html.parser")
    # Keep DOM order. Betshoot free rows expose team pair followed by 12 market prices.
    tokens=[" ".join(x.split()) for x in soup.stripped_strings]
    out=[]
    for i,t in enumerate(tokens):
        m=PAIR_RE.match(t)
        if not m: continue
        home,away=m.group(1).strip(),m.group(2).strip()
        if len(home)<2 or len(away)<2 or any(z in t.lower() for z in ("dropping odds","football odds")): continue
        vals=[]
        for x in tokens[i+1:i+36]:
            if PAIR_RE.match(x) and vals: break
            mm=ODD_RE.fullmatch(x.replace(" i",""))
            if mm:
                try: vals.append(float(mm.group(1)))
                except ValueError: pass
            if len(vals)>=12: break
        if len(vals)>=12:
            out.append({"source":"Betshoot","home":home,"away":away,"signals":_signals(vals[:12]),
                        "odds":vals[:12],"raw":t})
    # de-duplicate
    uniq={}
    for x in out: uniq[(x["home"].lower(),x["away"].lower())]=x
    return list(uniq.values())


class BetshootCollector:
    def collect(self, primary):
        meta={"site_reached":False,"events_read":0,"matched":0,"error":""}
        try:
            r=requests.get(URL,headers=HEADERS,timeout=25); r.raise_for_status(); meta["site_reached"]=True
            events=parse_html(r.text); meta["events_read"]=len(events)
            found={}
            for row in primary:
                best=None; best_sc=0.0
                for ev in events:
                    sc=match_score(row.get("home",""),row.get("away",""),ev["home"],ev["away"])
                    if sc>best_sc: best,best_sc=ev,sc
                if best and best_sc>=0.68:
                    found[(row.get("home"),row.get("away"))]={**best,"similarity":round(best_sc,3)}
            meta["matched"]=len(found)
            return found,meta
        except Exception as e:
            meta["error"]=str(e); return {},meta
