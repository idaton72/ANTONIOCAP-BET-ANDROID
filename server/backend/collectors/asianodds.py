import os,re,json
from pathlib import Path
from ..models import MatchData
from .base import fnum
from ..asianodds_credentials import load_credentials

DEBUG_DIR=Path.home()/"BetProfessional_Debug"
ARROWS="↑↓→"
RATING_RE=re.compile(r"\s+\d{3,4}(?=\s|$)")

def clean_num(s):
    if s is None:return None
    return fnum(str(s).translate(str.maketrans("","","↑↓→")))

def clean_team_text(s):
    s=(s or "").replace("☆"," ").replace("⚽"," ")
    s=RATING_RE.sub(" ",s)
    return " ".join(s.split()).strip()

def split_teams(match_text):
    raw=clean_team_text(match_text)
    # The live AsianOdds DOM does not provide a separator; use ratings from the
    # original string as anchors when both are present.
    original=(match_text or "").replace("☆"," ").replace("⚽"," ")
    parts=re.split(r"\s+\d{3,4}\s+",original.strip(),maxsplit=1)
    if len(parts)==2:
        home=" ".join(parts[0].split()).strip()
        away=re.sub(r"\s+\d{3,4}\s*$","",parts[1]).strip()
        if home and away:return home,away
    # Football icon often separates teams in some rows.
    iconparts=[x.strip() for x in (match_text or "").replace("☆","").split("⚽") if x.strip()]
    if len(iconparts)>=2:
        home=re.sub(r"\s+\d{3,4}\s*$","",iconparts[0]).strip()
        away=re.sub(r"\s+\d{3,4}\s*$","",iconparts[1]).strip()
        if home and away:return home,away
    return raw,""

def parse_primary(c, secondary, day):
    if len(c)<21:return None
    home,away=split_teams(c[2])
    if not home or not away:return None
    ml_open=[clean_num(x) for x in c[5].split()]
    ml_curr=[clean_num(x) for x in c[6].split()]
    # primary row = home side for AH and Over/GG side for totals/BTTS
    m=MatchData(home,away,day,kickoff=c[1],league=c[0].replace("☆","").strip(),
        source="AsianOdds",raw_text=" | ".join(c+secondary)[:5000])
    m.fav_spread_open=clean_num(c[7])
    m.fav_price_open=clean_num(c[8])
    m.fav_spread_current=clean_num(c[9])
    m.fav_price_current=clean_num(c[10])
    m.total_open=clean_num(c[11])
    m.over_price_open=clean_num(c[12])
    m.total_current=clean_num(c[13])
    m.over_price_current=clean_num(c[14])
    # second DOM row: opposite AH price, Under price, NG price
    if len(secondary)>=6:
        m.dog_price_open=clean_num(secondary[1]) if hasattr(m,"dog_price_open") else None
        m.dog_price_current=clean_num(secondary[3])
        m.under_price_open=clean_num(secondary[4])
        m.under_price_current=clean_num(secondary[5])
    # Attach ML data dynamically; engine V4.4 can use it.
    m.ml_home_open=ml_open[0] if len(ml_open)>0 else None
    m.ml_draw_open=ml_open[1] if len(ml_open)>1 else None
    m.ml_away_open=ml_open[2] if len(ml_open)>2 else None
    m.ml_home_current=ml_curr[0] if len(ml_curr)>0 else None
    m.ml_draw_current=ml_curr[1] if len(ml_curr)>1 else None
    m.ml_away_current=ml_curr[2] if len(ml_curr)>2 else None
    m.btts_gg_open=clean_num(c[16])
    m.btts_gg_current=clean_num(c[17])
    if len(secondary)>=9:
        m.btts_ng_open=clean_num(secondary[7])
        m.btts_ng_current=clean_num(secondary[8])
    return m

class AsianOddsCollector:
    async def fetch(self,day,cfg):
        from playwright.async_api import async_playwright
        DEBUG_DIR.mkdir(parents=True,exist_ok=True)
        raw=[]
        async with async_playwright() as p:
            args={"headless":cfg.get("headless",True)}
            bp=os.environ.get("BETPROFESSIONAL_CHROMIUM")
            if bp:args["executable_path"]=bp
            browser=await p.chromium.launch(**args)
            page=await browser.new_page(viewport={"width":1920,"height":1400})
            try:
                await page.goto(cfg["url"],wait_until="domcontentloaded",timeout=90000)
                await page.wait_for_timeout(3000)

                # Authorized account login. Credentials stay in Windows Credential Manager,
                # never in source code/configuration files.
                username,password=load_credentials()
                if username and password:
                    # Try common login entry points/fields without storing secrets in logs.
                    try:
                        login_link=page.get_by_role("link",name=re.compile("login|sign in|accedi",re.I))
                        if await login_link.count():
                            await login_link.first.click()
                            await page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    try:
                        uf=page.locator('input[type="email"],input[name*="email" i],input[name*="user" i]').first
                        pf=page.locator('input[type="password"]').first
                        if await uf.count() and await pf.count():
                            await uf.fill(username); await pf.fill(password)
                            btn=page.locator('button[type="submit"],input[type="submit"]').first
                            if await btn.count(): await btn.click()
                            else: await pf.press("Enter")
                            await page.wait_for_timeout(3500)
                            if "next-games" not in page.url:
                                await page.goto(cfg["url"],wait_until="domcontentloaded",timeout=90000)
                    except Exception:
                        pass

                # Load all rows exposed to the authorized session (lazy loading / scrolling).
                stable=0; last=-1
                for _ in range(60):
                    count=await page.locator("table tbody tr").count()
                    if count==last: stable+=1
                    else: stable=0; last=count
                    if stable>=4: break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    # Click a normal 'load more/show more' control if the page provides one.
                    try:
                        more=page.get_by_role("button",name=re.compile("load more|show more|more|carica|mostra",re.I))
                        if await more.count() and await more.first.is_visible():
                            await more.first.click()
                    except Exception: pass
                    await page.wait_for_timeout(700)
                await page.evaluate("window.scrollTo(0,0)")
                await page.wait_for_timeout(1000)
                (DEBUG_DIR/"asianodds_debug.html").write_text(await page.content(),encoding="utf-8")
                # Snapshot atomico del DOM: AsianOdds aggiorna dinamicamente le righe.
                # Evita timeout su locator nth(i)/nth(j) quando una riga cambia durante la lettura.
                snapshot = await page.evaluate("""() => Array.from(document.querySelectorAll('table')).map((table, ti) => ({
                    table: ti,
                    headers: Array.from(table.querySelectorAll('thead th')).map(x => (x.innerText || '').replace(/\\s+/g,' ').trim()),
                    rows: Array.from(table.querySelectorAll('tbody tr')).map(tr =>
                        Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').replace(/\\s+/g,' ').trim())
                    )
                }))""")
                for t in snapshot:
                    headers=t.get("headers",[])
                    for vals in t.get("rows",[]):
                        raw.append({"table":t.get("table",0),"headers":headers,"cells":vals})
            finally:await browser.close()
        (DEBUG_DIR/"asianodds_rows.json").write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8")
        out=[];i=0
        while i<len(raw):
            c=raw[i]["cells"]
            if len(c)>=20 and len(c)>2 and ("1 X 2" in c or (len(c)>4 and c[4]=="1 X 2")):
                sec=raw[i+1]["cells"] if i+1<len(raw) and len(raw[i+1]["cells"])<=12 else []
                m=parse_primary(c,sec,day)
                if m:out.append(m)
                i+=2 if sec else 1
            else:i+=1
        return out
