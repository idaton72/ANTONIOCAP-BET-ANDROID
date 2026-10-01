import os, re, unicodedata, json
from pathlib import Path
from difflib import SequenceMatcher
from .generic import GenericCollector

DEBUG_DIR=Path.home()/"BOLLETTONEFACILE_Debug"

SOURCES = [
    ("BTFOdds", "https://www.btfodds.com/soccer/football-odds-trends/dropping-odds,all,today,average,UO,league"),
    ("AsianBetSoccer", "https://www.asianbetsoccer.com/nextgame.html#"),
    ("ArbWorld", "https://arbworld.net/it/dropping-odds/football/1x2"),
]

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode()
    s = s.lower().replace("&"," and ")
    s = re.sub(r"\b(fc|cf|sc|afc|fk|ac|calcio|club)\b"," ",s)
    s = re.sub(r"[^a-z0-9]+"," ",s)
    return " ".join(s.split())

def similarity(a,b):
    return SequenceMatcher(None,norm(a),norm(b)).ratio()

def match_score(a_home,a_away,b_home,b_away):
    direct=(similarity(a_home,b_home)+similarity(a_away,b_away))/2
    reverse=(similarity(a_home,b_away)+similarity(a_away,b_home))/2
    return max(direct,reverse)

def signal_from_text(text, source):
    t=(text or "").lower()
    sig=[]
    # Conservative: source presence is separated from directional confirmation.
    if source=="BTFOdds" and any(x in t for x in ["over","o/u","dropping","under/over"]):
        sig.append("TOTAL_MARKET")
    if source=="AsianBetSoccer":
        if "blue" in t or "total" in t or "over" in t: sig.append("TOTAL_LINE")
    if source=="ArbWorld":
        if any(x in t for x in ["drop","dropping","1x2","odds"]): sig.append("1X2_DROP")
    return sig


def _nums(cell):
    return [float(x) for x in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", cell or "")]

def _split_event(event):
    parts=re.split(r"\s+(?:-|–|—|vs\.?|v)\s+", event or "", maxsplit=1, flags=re.I)
    if len(parts)!=2: return None
    h,a=(x.strip() for x in parts)
    return (h,a) if len(h)>1 and len(a)>1 else None

def _btfodds(rows):
    out=[]
    for r in rows:
        c=r.get("cells",[])
        # Date | Event | 1 | X | 2 | U2.5 | O2.5 | St
        if len(c)<7 or not _split_event(c[1] if len(c)>1 else ""):
            continue
        h,a=_split_event(c[1])
        signals=[]

        # 1/X/2: each cell normally contains opening + current quote.
        for outcome,idx in (("1",2),("X",3),("2",4)):
            vals=_nums(c[idx]) if len(c)>idx else []
            if len(vals)>=2 and vals[-1] < vals[0]:
                signals.append(f"1X2_DROP_{outcome}")

        ov=_nums(c[6])
        if len(ov)>=2 and ov[-1] < ov[0]:
            pct=round((ov[0]-ov[-1])/ov[0]*100,1)
            signals.append(f"OVER25_DROP_{pct}%")

        out.append({
            "source":"BTFOdds","home":h,"away":a,
            "raw":" | ".join(c),"signals":signals,
            "over25_open":ov[0] if ov else None,
            "over25_current":ov[-1] if ov else None
        })
    return out

def _arbworld(rows):
    out=[]
    # The first cell contains date/time + league + "Home — Away".
    # Extract teams from the em-dash, then remove the fixed date/time prefix
    # from the home side. League words remain before home, so use candidates:
    # full left and suffixes; enrich() resolves them conservatively.
    for r in rows:
        c=r.get("cells",[])
        if len(c)!=5 or "—" not in c[0]: continue
        left,away=[x.strip() for x in c[0].rsplit("—",1)]
        left=re.sub(r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{2}:\d{2}\s+","",left)
        # Build suffix candidates because ArbWorld concatenates league + home.
        words=left.split()
        candidates=[]
        for n in range(1,min(7,len(words))+1):
            h=" ".join(words[-n:])
            if len(h)>=2: candidates.append(h)
        drops=[]
        for market,cell in zip(("1","X","2"),c[1:4]):
            nums=_nums(cell)
            if ("▼" in cell or (len(nums)>=2 and nums[-1]<nums[0])):
                drops.append(market)
        sig=["1X2_DROP_"+"/".join(drops)] if drops else []
        for h in candidates:
            out.append({"source":"ArbWorld","home":h,"away":away,
                        "raw":" | ".join(c),"signals":sig})
    return out

def _asianbetsoccer(rows):
    out=[]
    # Current site sometimes exposes only filters/header rows. We accept
    # a row ONLY when an actual fixture separator is present; no fabricated bonus.
    for r in rows:
        c=r.get("cells",[])
        if len(c)<2: continue
        event=None
        for cell in c:
            if _split_event(cell):
                event=cell; break
        if not event: continue
        h,a=_split_event(event)
        # Real game rows on this site carry the Total Line/Over columns.
        # Presence of a populated game row is recorded, but only explicit
        # over/total-line evidence can confirm.
        raw=" | ".join(c)
        sig=[]
        low=raw.lower()
        if "over" in low or "total line" in low or re.search(r"\bov\b",low):
            sig.append("TOTAL_LINE")
        out.append({"source":"AsianBetSoccer","home":h,"away":a,
                    "raw":raw,"signals":sig})
    return out

async def _block_heavy(route):
    """Riduce memoria/rete nei collector secondari senza toccare HTML/JS/XHR."""
    try:
        if route.request.resource_type in {"image","media","font"}:
            await route.abort()
        else:
            await route.continue_()
    except Exception:
        try: await route.continue_()
        except Exception: pass

async def collect_secondary(day,cfg):
    from playwright.async_api import async_playwright
    DEBUG_DIR.mkdir(parents=True,exist_ok=True)
    results=[]
    async with async_playwright() as p:
        args={"headless":cfg.get("headless",True)}
        bp=os.environ.get("BETPROFESSIONAL_CHROMIUM")
        if bp: args["executable_path"]=bp
        browser=await p.chromium.launch(**args)
        try:
            for name,url in SOURCES:
                page=await browser.new_page(viewport={"width":1920,"height":1400})
                await page.route("**/*", _block_heavy)
                slug=name.lower()
                debug_rows=[]
                try:
                    await page.goto(url,wait_until="domcontentloaded",timeout=90000)
                    await page.wait_for_timeout(4500)
                    (DEBUG_DIR/f"{slug}_debug.html").write_text(await page.content(),encoding="utf-8")

                    # Capture main page AND child frames: useful for AsianBetSoccer.
                    for fi,frame in enumerate(page.frames):
                        try:
                            tables=frame.locator("table")
                            for ti in range(await tables.count()):
                                table=tables.nth(ti)
                                headers=[]
                                th=table.locator("thead th")
                                for j in range(await th.count()):
                                    headers.append(" ".join((await th.nth(j).inner_text()).split()))
                                trs=table.locator("tr")
                                for ri in range(await trs.count()):
                                    cells_loc=trs.nth(ri).locator("th,td")
                                    cells=[" ".join((await cells_loc.nth(j).inner_text()).split())
                                           for j in range(await cells_loc.count())]
                                    if cells:
                                        debug_rows.append({"frame":fi,"table":ti,"row":ri,
                                                           "headers":headers,"cells":cells})
                        except Exception:
                            pass

                    (DEBUG_DIR/f"{slug}_rows.json").write_text(
                        json.dumps(debug_rows,ensure_ascii=False,indent=2),encoding="utf-8")

                    if name=="BTFOdds": parsed=_btfodds(debug_rows)
                    elif name=="ArbWorld": parsed=_arbworld(debug_rows)
                    else: parsed=_asianbetsoccer(debug_rows)
                    results.extend(parsed)
                except Exception as e:
                    results.append({"source":name,"error":str(e)})
                    (DEBUG_DIR/f"{slug}_error.txt").write_text(str(e),encoding="utf-8")
                finally:
                    await page.close()
        finally:
            await browser.close()
    return results

def enrich(primary, secondary, threshold=0.68):
    for r in primary:
        h,a=r["home"],r["away"]
        all_candidates=[]
        for x in secondary:
            if x.get("error") or not x.get("home"): continue
            sc=match_score(h,a,x["home"],x["away"])
            all_candidates.append({
                "source":x["source"],"similarity":round(sc,3),
                "candidate":f'{x["home"]} – {x["away"]}',
                "signals":x.get("signals",[]),"raw":x.get("raw","")
            })

        diagnostics={}
        confirmed=[]
        best_matches=[]
        for src in ["BTFOdds","AsianBetSoccer","ArbWorld"]:
            cand=sorted([x for x in all_candidates if x["source"]==src],
                        key=lambda x:x["similarity"],reverse=True)[:3]
            best=cand[0] if cand else None
            diagnostics[src]={
                "best_similarity": best["similarity"] if best else 0,
                "best_candidate": best["candidate"] if best else "",
                "signals": best["signals"] if best else [],
                "accepted": bool(best and best["similarity"]>=threshold and best["signals"]),
                "top3": cand
            }
            if diagnostics[src]["accepted"]:
                confirmed.append(src)
                best_matches.append(best)

        bonus=min(24,len(confirmed)*8)
        r["base_score"]=r["score"]
        r["confirmations"]=confirmed
        r["matching_diagnostics"]=diagnostics
        r["source_matches"]=best_matches
        r["multisource_bonus"]=bonus
        r["score"]=min(100,r["score"]+bonus)
        if confirmed:r["reasons"].append("Conferme: "+", ".join(confirmed))
        r["source"]="AsianOdds" + (" + "+"/".join(confirmed) if confirmed else "")
    return sorted(primary,key=lambda x:(x["score"],len(x.get("confirmations",[]))),reverse=True)
