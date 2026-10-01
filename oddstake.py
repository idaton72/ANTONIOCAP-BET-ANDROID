import re, unicodedata, os
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

URL="https://oddstake.com/odds/"


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


def _decimal(cell):
    # Oddstake can display fractional + decimal in the same cell (e.g. 133/100 1.33).
    vals=re.findall(r"(?<![/\d])(\d{1,3}(?:[\.,]\d{1,2})?)(?![/\d])", cell or "")
    nums=[]
    for x in vals:
        try:
            v=float(x.replace(",","."))
            if 1.01 <= v <= 100: nums.append(v)
        except: pass
    return nums[-1] if nums else None


def _pct(cell):
    m=re.search(r"(\d{1,3})\s*%",cell or "")
    return int(m.group(1)) if m else None


def extract_events(html):
    soup=BeautifulSoup(html,"html.parser")
    events=[]; seen=set()
    for tr in soup.find_all("tr"):
        tds=tr.find_all("td")
        if len(tds)<9: continue
        cells=[" ".join(td.get_text(" ",strip=True).split()) for td in tds]
        # Current layout: KICK OFF | HOME TEAM | % | HOME | DRAW | AWAY | % | AWAY TEAM | PREDICTION
        if not re.search(r"\b\d{1,2}:\d{2}\b",cells[0]): continue
        home,away=cells[1].strip(),cells[7].strip()
        if not home or not away or norm(home)==norm(away): continue
        pred=cells[8].strip().upper()
        if not pred: continue
        key=(norm(home),norm(away))
        if key in seen: continue
        seen.add(key)
        events.append({
            "home":home,"away":away,"home_pct":_pct(cells[2]),"away_pct":_pct(cells[6]),
            "odds_1":_decimal(cells[3]),"odds_x":_decimal(cells[4]),"odds_2":_decimal(cells[5]),
            "prediction":pred,"row":" | ".join(cells)[:1000]
        })
    return events


def prediction_pick(prediction):
    p=(prediction or "").upper().strip()
    if p=="HOME WIN": return "1"
    if p=="AWAY WIN": return "2"
    # DNB/DC are deliberately not converted to a strict 1X2 pick.
    return None


class OddstakeCollector:
    async def collect(self,fixtures):
        out={}; diag=[]
        meta={"site_reached":False,"events_read":0,"matched":0,"http_status":None}
        p=browser=page=None
        try:
            p=await async_playwright().start()
            args={"headless":True}
            bp=os.environ.get("BETPROFESSIONAL_CHROMIUM")
            if bp: args["executable_path"]=bp
            browser=await p.chromium.launch(**args)
            page=await browser.new_page(viewport={"width":1800,"height":1400},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36")
            resp=await page.goto(URL,wait_until="domcontentloaded",timeout=60000)
            meta["site_reached"]=True
            if resp: meta["http_status"]=resp.status
            try: await page.wait_for_load_state("networkidle",timeout=12000)
            except: pass
            await page.wait_for_timeout(1200)
            events=extract_events(await page.content()); meta["events_read"]=len(events)
            for f in fixtures:
                h,a=f.get("home",""),f.get("away","")
                best=(0,None)
                for e in events:
                    direct=(sim(h,e["home"])+sim(a,e["away"]))/2
                    reverse=(sim(h,e["away"])+sim(a,e["home"]))/2
                    sc=max(direct,reverse-0.10)
                    if sc>best[0]: best=(sc,e)
                if best[1] and best[0]>=.60:
                    e=best[1]; d={"ok":True,"similarity":round(best[0],3),**e,"pick":prediction_pick(e["prediction"])}
                    out[(norm(h),norm(a))]=d; diag.append({"match":f"{h} - {a}",**d})
                else:
                    diag.append({"match":f"{h} - {a}","ok":False,"reason":f"non abbinata | Oddstake lette={len(events)}"})
            meta["matched"]=len(out)
        except Exception as e:
            meta["error"]=str(e)
            diag=[{"match":f'{f.get("home")} - {f.get("away")}',"ok":False,"reason":str(e)} for f in fixtures]
        finally:
            try:
                if browser: await browser.close()
            except: pass
            try:
                if p: await p.stop()
            except: pass
        return out,diag,meta
