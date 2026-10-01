import re, unicodedata, os
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

URL="https://www.oddsmath.com/football/matches/today/"

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    s=re.sub(r"\b(fc|cf|sc|afc|fk|ac|club|calcio|sv|sk|af)\b"," ",s)
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

def sim(a,b):
    a,b=norm(a),norm(b)
    if not a or not b:return 0.0
    if a==b:return 1.0
    if a in b or b in a:return .92
    return SequenceMatcher(None,a,b).ratio()

async def _launch_page():
    p=await async_playwright().start()
    args={"headless":True}
    bp=os.environ.get("BETPROFESSIONAL_CHROMIUM")
    if bp: args["executable_path"]=bp
    browser=await p.chromium.launch(**args)
    page=await browser.new_page(
        viewport={"width":1600,"height":1200},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
    )
    resp=await page.goto(URL,wait_until="domcontentloaded",timeout=45000)
    try: await page.wait_for_load_state("networkidle",timeout=15000)
    except: pass
    await page.wait_for_timeout(1800)
    return p,browser,page,resp

def _float(s):
    try:return float(str(s).replace(",","."))
    except:return None

def extract_events(html):
    """
    OddsMath oggi espone righe tipo:
    16:30 | Home | - | Away | status | BN | 1 | X | 2 | margin

    Non dipendiamo più dal formato dell'href: riconosciamo la riga
    dalla presenza dell'orario + almeno due link squadra + quote 1X2.
    """
    soup=BeautifulSoup(html,"html.parser")
    events=[]
    seen=set()
    for tr in soup.find_all("tr"):
        tds=tr.find_all("td")
        if len(tds)<7:
            continue
        cells=[" ".join(td.get_text(" ",strip=True).split()) for td in tds]
        if not any(re.fullmatch(r"\d{1,2}:\d{2}", c) for c in cells[:2]):
            continue

        anchors=[]
        for a in tr.find_all("a"):
            txt=" ".join(a.get_text(" ",strip=True).split())
            if txt and txt not in anchors:
                anchors.append(txt)

        # Nelle righe-evento i primi due anchor testuali sono le due squadre.
        if len(anchors)<2:
            # fallback: team names are commonly cells 1 and 3
            possible=[c for c in cells[1:5] if c and c not in ("-","‐","–")]
            if len(possible)>=2:
                anchors=possible[:2]
            else:
                continue

        home,away=anchors[0],anchors[1]
        if norm(home)==norm(away):
            continue

        # Quote: le tre celle prima del margine sono quasi sempre 1 X 2.
        odds=[]
        for c in cells:
            v=_float(c)
            if v is not None and 1.01<=v<=100:
                odds.append(v)
        if len(odds)<3:
            continue

        # Evita di prendere BN (numero bookmaker) come quota:
        # seleziona le ultime 3 quote plausibili prima dell'eventuale margine.
        one,x,two=odds[-3:]
        key=(norm(home),norm(away))
        if key in seen: continue
        seen.add(key)
        events.append({
            "home":home,"away":away,
            "odds_1":one,"odds_x":x,"odds_2":two,
            "odds":[one,x,two],
            "row":" | ".join(cells)[:800]
        })
    return events

class OddsMathCollector:
    async def collect(self,fixtures):
        out={};diag=[]
        meta={"site_reached":False,"events_read":0,"matched":0,"http_status":None}
        p=browser=page=None
        try:
            p,browser,page,resp=await _launch_page()
            meta["site_reached"]=True
            if resp: meta["http_status"]=resp.status
            html=await page.content()
            events=extract_events(html)
            meta["events_read"]=len(events)

            for f in fixtures:
                h,a=f.get("home",""),f.get("away","")
                best=(0,None)
                for e in events:
                    direct=(sim(h,e["home"])+sim(a,e["away"]))/2
                    reverse=(sim(h,e["away"])+sim(a,e["home"]))/2
                    sc=max(direct,reverse-0.08)
                    if sc>best[0]:best=(sc,e)

                if best[1] and best[0]>=.57:
                    e=best[1]
                    d={"ok":True,"similarity":round(best[0],3),
                       "site_home":e["home"],"site_away":e["away"],
                       "odds":e["odds"],"odds_1":e["odds_1"],
                       "odds_x":e["odds_x"],"odds_2":e["odds_2"],
                       "row":e["row"]}
                    out[(norm(h),norm(a))]=d
                    diag.append({"match":f"{h} - {a}",**d})
                else:
                    diag.append({"match":f"{h} - {a}","ok":False,
                                 "reason":f"non abbinata | OddsMath letti={len(events)}"})
            meta["matched"]=len(out)
        except Exception as e:
            meta["error"]=str(e)
            diag=[{"match":f'{f.get("home")} - {f.get("away")}',
                   "ok":False,"reason":str(e)} for f in fixtures]
        finally:
            try:
                if browser: await browser.close()
            except: pass
            try:
                if p: await p.stop()
            except: pass
        return out,diag,meta
