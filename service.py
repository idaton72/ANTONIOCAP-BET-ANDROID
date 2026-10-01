from backend.collectors.forebet import ForebetCollector, attach as attach_forebet
from backend.collectors.afootballreport import AFootballReportCollector, attach as attach_afr
from backend.collectors.footystats import FootyStatsCollector, attach as attach_footystats
from backend.collectors.soccerstats247 import SoccerStats247Collector, attach as attach_soccerstats247
import json
from pathlib import Path
from .collectors.asianodds import AsianOddsCollector
from .collectors.multisource import collect_secondary,enrich
from .engine import evaluate
from .engine_1x2 import enrich_1x2
from .engine_finalbet import apply_final_bets
from .engine_multimethod import apply_multimethod, load_stats_csv, stats_count, set_stats_dict, merge_stats_dict
from .collectors.oddsmath import OddsMathCollector
from .collectors.oddstake import OddstakeCollector
from .collectors.auto_stats import build_market_stats
from .nowgoalbet_signal import attach_nowgoalbet
from .golbet_engine import attach_golbet
from .collectors.football_data_history import FootballDataHistoryCollector
from .collectors.api_football_history import ApiFootballHistoryCollector
from .collectors.betshoot import BetshootCollector

import re as _re, unicodedata as _unicodedata
def _norm_team(value):
    x=_unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    x=_re.sub(r"\\b(fc|cf|sc|afc|fk|ac|club|calcio)\\b"," ",x)
    return " ".join(_re.sub(r"[^a-z0-9]+"," ",x).split())

CFG=Path(__file__).with_name("config.json")
def config():return json.loads(CFG.read_text(encoding="utf-8"))

def calibrate_goal_multisource(rows):
    """
    Recalibra SOLO lo score GOAL/OVER dopo il matching multisource.
    Non modifica pick, reasons, scraping o matching.

    Regole:
    - base score interno del motore GOAL viene compresso;
    - nessuna conferma esterna: max 79;
    - 1 conferma esterna: max 89;
    - 2+ conferme esterne: max 95;
    - per arrivare a 90+ servono almeno 2 conferme;
    - preserva l'ordinamento relativo del motore originale.
    """
    for r in rows:
        raw_score=int(r.get("score",0) or 0)
        confirmations=list(r.get("confirmations",[]) or [])
        nconf=len(confirmations)

        # compressione morbida del punteggio originale
        # 100 -> 82 prima dei limiti multisource
        compressed=round(raw_score * 0.82)

        if nconf == 0:
            final=min(79, compressed)
        elif nconf == 1:
            # una conferma può portare fino a 89
            final=min(89, compressed + 8)
        else:
            # due o più conferme: fascia eccellente consentita
            final=min(95, compressed + 16)

        # evita di promuovere troppo segnali originariamente deboli
        if raw_score < 60:
            final=min(final,69)
        elif raw_score < 75:
            final=min(final,79)

        r["goal_score_raw"]=raw_score
        r["goal_score_calibrated"]=final
        r["score"]=final

        if nconf == 0:
            r.setdefault("reasons",[]).append("GOAL calibrato: nessuna conferma esterna")
        elif nconf == 1:
            r.setdefault("reasons",[]).append(f"GOAL calibrato: 1 conferma ({confirmations[0]})")
        else:
            r.setdefault("reasons",[]).append("GOAL calibrato: conferme multiple")

    return rows


def attach_market_value(rows):
    """Aggiunge quota corrente e indice comparativo VALORE senza modificare i pronostici."""
    for r in rows:
        raw=r.get("raw",{}) or {}

        pick=r.get("pick_1x2")
        q1x2=None
        if pick=="1": q1x2=raw.get("ml_home_current")
        elif pick=="X": q1x2=raw.get("ml_draw_current")
        elif pick=="2": q1x2=raw.get("ml_away_current")
        try: q1x2=float(q1x2) if q1x2 is not None else None
        except: q1x2=None
        r["quota_1x2"]=q1x2
        r["valore_1x2"]=round((r.get("score_1x2",0) or 0)*q1x2/100,2) if q1x2 else None

        gp=(r.get("pick") or "").upper()
        qgoal=None
        if "GG + OVER" in gp:
            vals=[]
            for k in ("btts_gg_current","over_price_current"):
                try:
                    if raw.get(k) is not None: vals.append(float(raw.get(k)))
                except: pass
            if vals: qgoal=max(vals)
        elif "OVER 2,5" in gp:
            try: qgoal=float(raw.get("over_price_current")) if raw.get("over_price_current") is not None else None
            except: qgoal=None
        elif gp=="GG":
            try: qgoal=float(raw.get("btts_gg_current")) if raw.get("btts_gg_current") is not None else None
            except: qgoal=None

        r["quota_goal"]=qgoal
        r["valore_goal"]=round((r.get("score",0) or 0)*qgoal/100,2) if qgoal else None
    return rows


def _diag_accepted(row, source):
    d=(row.get("matching_diagnostics",{}) or {}).get(source,{}) or {}
    return bool(d.get("accepted")), list(d.get("signals",[]) or [])

def _oddsmath_favourite(row):
    odds=row.get("oddsmath_odds",[]) or []
    if len(odds)<3: return None
    try: vals=[float(x) for x in odds[:3]]
    except Exception: return None
    return ("1","X","2")[min(range(3),key=lambda k: vals[k])]

def apply_multisource_score(rows):
    for r in rows:
        coverage={"AsianOdds":True,"BTFOdds":False,"AsianBetSoccer":False,"ArbWorld":False,"Betshoot":bool(r.get("betshoot_available")),"OddsMath":bool(r.get("oddsmath_available")),"Oddstake":bool(r.get("oddstake_available")),"NowGoalBet":bool(r.get("nowgoalbet_available")),"GolBet":bool(r.get("golbet_available"))}
        for src in ("BTFOdds","AsianBetSoccer","ArbWorld"):
            d=(r.get("matching_diagnostics",{}) or {}).get(src,{}) or {}
            coverage[src]=bool(d.get("best_similarity",0)>=0.68)
        r["source_coverage"]=coverage
        r["source_indicator"]=" | ".join(f"{k} {'OK' if v else '--'}" for k,v in coverage.items())

        pick=r.get("pick_1x2")
        core=int(r.get("score_1x2",0) or 0)
        xs=["AsianOdds"] if pick and pick!="NO BET" and core>0 else []
        xc=[]
        if pick and pick!="NO BET":
            for src in ("BTFOdds","ArbWorld"):
                accepted,signals=_diag_accepted(r,src)
                if not accepted: continue
                same=False; other=False
                for sig in signals:
                    if not sig.startswith("1X2_DROP_"): continue
                    outs=sig.split("1X2_DROP_",1)[1].split("/")
                    same |= pick in outs
                    other |= any(o in ("1","X","2") and o!=pick for o in outs)
                if same: xs.append(src)
                elif other: xc.append(src)
            if r.get("betshoot_available"):
                bsigs=r.get("betshoot_signals",[]) or []
                same=any(sig.startswith(f"BETSHOOT_DROP_{pick}_") for sig in bsigs)
                other=any(sig.startswith(f"BETSHOOT_DROP_{o}_") for o in ("1","X","2") if o!=pick for sig in bsigs)
                if same: xs.append("Betshoot")
                elif other: xc.append("Betshoot")
            if r.get("oddsmath_available"):
                fav=_oddsmath_favourite(r)
                if fav==pick: xs.append("OddsMath")
                elif fav: xc.append(f"OddsMath({fav})")
            if r.get("oddstake_available"):
                op=r.get("oddstake_pick")
                pred=r.get("oddstake_prediction","")
                if op==pick: xs.append("Oddstake")
                elif op: xc.append(f"Oddstake({op})")
                # DC/DNB remain diagnostic/supporting data only; never force 1X2.
                r["oddstake_soft_signal"]=pred if not op else ""
            # NOWGOALBET: exact 1/X/2 can confirm/conflict; 1X/X2 stay soft diagnostics.
            ng=r.get("nowgoalbet_signal")
            if ng in ("1","X","2"):
                if ng==pick: xs.append("NowGoalBet")
                else: xc.append(f"NowGoalBet({ng})")
            r["nowgoalbet_soft_signal"]=ng if ng in ("1X","X2") else ""
        xscore=core
        if core>0:
            if "OddsMath" in xs: xscore+=5
            if "Oddstake" in xs: xscore+=4
            if "NowGoalBet" in xs: xscore+=3
            xscore-=4*len(xc)
            xscore=max(0,min(95,xscore))
        r["multisource_1x2_score"]=xscore; r["multisource_1x2_support"]=xs; r["multisource_1x2_conflict"]=xc

        gp=(r.get("pick") or "").upper()
        graw=int(r.get("goal_score_raw",r.get("score",0)) or 0)
        gs=["AsianOdds"] if gp and gp!="DA VERIFICARE" and graw>0 else []
        if gp and gp!="DA VERIFICARE":
            accepted,signals=_diag_accepted(r,"BTFOdds")
            if accepted and any(sig.startswith("OVER25_DROP_") or sig=="TOTAL_MARKET" for sig in signals): gs.append("BTFOdds")
            accepted,signals=_diag_accepted(r,"AsianBetSoccer")
            if accepted and any(sig=="TOTAL_LINE" for sig in signals): gs.append("AsianBetSoccer")
            if r.get("betshoot_available"):
                bsigs=r.get("betshoot_signals",[]) or []
                if "OVER 2,5" in gp and any(sig.startswith("BETSHOOT_DROP_OVER25_") for sig in bsigs): gs.append("Betshoot")
                elif "GG" in gp and any(sig.startswith("BETSHOOT_DROP_BTTS_") for sig in bsigs): gs.append("Betshoot")
        compressed=round(graw*0.82)
        extra=max(0,len(gs)-1)
        if extra==0:gscore=min(79,compressed)
        elif extra==1:gscore=min(89,compressed+8)
        else:gscore=min(95,compressed+16)
        if graw<60:gscore=min(gscore,69)
        elif graw<75:gscore=min(gscore,79)
        r["multisource_goal_score"]=max(0,gscore); r["multisource_goal_support"]=gs

        choices=[]
        if xscore>0 and pick and pick!="NO BET": choices.append((xscore,"1X2",pick,xs,xc))
        if gscore>0 and gp and gp!="DA VERIFICARE": choices.append((gscore,"GOAL",r.get("pick",""),gs,[]))
        if choices:
            sc,mkt,pp,supp,conf=max(choices,key=lambda x:x[0])
            r["multisource_score"]=int(sc); r["multisource_market"]=mkt; r["multisource_pick"]=pp
            r["multisource_support"]=supp; r["multisource_conflict"]=conf
        else:
            r["multisource_score"]=0; r["multisource_market"]="--"; r["multisource_pick"]="NO BET"
            r["multisource_support"]=[]; r["multisource_conflict"]=[]
    return rows

async def collect_all(day):
    cfg=config();status=[]
    primary=[]
    try:
        primary=await AsianOddsCollector().fetch(day,{**cfg,"url":"https://asianodds.com/en/next-games"})
        status.append({"source":"AsianOdds","ok":True,"count":len(primary)})
    except Exception as e:
        status.append({"source":"AsianOdds","ok":False,"count":0,"error":str(e)})
    secondary=[]
    try:
        secondary=await collect_secondary(day,cfg)
        for name in ["BTFOdds","AsianBetSoccer","ArbWorld"]:
            errs=[x for x in secondary if x.get("source")==name and x.get("error")]
            rows=[x for x in secondary if x.get("source")==name and not x.get("error")]
            status.append({"source":name,"ok":not bool(errs),"count":len(rows),
                           "error":errs[0]["error"] if errs else ""})
    except Exception as e:
        status.append({"source":"Multisource","ok":False,"count":0,"error":str(e)})
    evaluated=[evaluate(x) for x in primary]
    base=attach_market_value(enrich_1x2(calibrate_goal_multisource(enrich(evaluated,secondary))))

    name="Betshoot"
    try:
        found,bmeta=BetshootCollector().collect(base)
        status.append({"source":name,"ok":bool(bmeta.get("site_reached")),"count":bmeta.get("matched",0),
                       "details":f"PUBBLICHE={bmeta.get('events_read',0)} | ABBINATE={bmeta.get('matched',0)} | mercati 1X2/O2.5/U2.5/BTTS",
                       "error":bmeta.get("error","")})
        for r in base:
            d=found.get((r.get("home"),r.get("away")))
            r["betshoot_available"]=bool(d)
            r["betshoot_signals"]=d.get("signals",[]) if d else []
            r["betshoot_similarity"]=d.get("similarity",0) if d else 0
    except Exception as e:
        status.append({"source":name,"ok":False,"count":0,"error":str(e)})
        for r in base: r["betshoot_available"]=False; r["betshoot_signals"]=[]

    name="OddsMath"
    try:
        found,diag,meta=await OddsMathCollector().collect(base)
        ok=sum(1 for x in diag if x.get("ok"))
        status.append({"source":name,"ok":bool(meta.get("site_reached")),"count":ok,
                       "details":f"SITO={'OK' if meta.get('site_reached') else 'NO'} | LETTE={meta.get('events_read',0)} | ABBINATE={meta.get('matched',ok)}",
                       "error":meta.get("error","")})
        bymatch={x.get("match"):x for x in diag}
        for r in base:
            key=(_norm_team(r.get("home")),_norm_team(r.get("away")))
            r["oddsmath_available"]=key in found
            r["oddsmath_diag"]=bymatch.get(f'{r.get("home")} - {r.get("away")}',{})
            if key in found:r["oddsmath_odds"]=found[key].get("odds",[])
    except Exception as e:
        status.append({"source":name,"ok":False,"count":0,"error":str(e)})

    name="Oddstake"
    try:
        found,diag,meta=await OddstakeCollector().collect(base)
        ok=sum(1 for x in diag if x.get("ok"))
        status.append({"source":name,"ok":bool(meta.get("site_reached")),"count":ok,
                       "details":f"SITO={'OK' if meta.get('site_reached') else 'NO'} | LETTE={meta.get('events_read',0)} | ABBINATE={meta.get('matched',ok)}",
                       "error":meta.get("error","")})
        bymatch={x.get("match"):x for x in diag}
        for r in base:
            key=(_norm_team(r.get("home")),_norm_team(r.get("away")))
            d=found.get(key)
            r["oddstake_available"]=bool(d)
            r["oddstake_diag"]=bymatch.get(f'{r.get("home")} - {r.get("away")}',{})
            if d:
                r["oddstake_prediction"]=d.get("prediction","")
                r["oddstake_pick"]=d.get("pick")
                r["oddstake_home_pct"]=d.get("home_pct")
                r["oddstake_away_pct"]=d.get("away_pct")
                r["oddstake_odds"]=[d.get("odds_1"),d.get("odds_x"),d.get("odds_2")]
    except Exception as e:
        status.append({"source":name,"ok":False,"count":0,"error":str(e)})

    # AUTO STORICO GOLBET: recupera le ultime 6 REALI dove il provider copre la lega.
    # Non sovrascrive mai lo storico CSV importato dall'utente.
    try:
        token=(config().get("football_data_token") or "").strip()
        hist,hmeta=FootballDataHistoryCollector(token).collect(base)
        added=merge_stats_dict(hist)
        status.append({"source":"GolBet AutoHistory","ok":bool(hmeta.get("configured") and hmeta.get("site_reached")),
                       "count":hmeta.get("complete",0),
                       "details":f"MATCH={hmeta.get('matched',0)} | 6 GARE COMPLETE={hmeta.get('complete',0)} | AGGIUNTE={added} | provider football-data.org",
                       "error":hmeta.get("error","")})
    except Exception as e:
        status.append({"source":"GolBet AutoHistory","ok":False,"count":0,"error":str(e)})

    # FALLBACK API-FOOTBALL: solo per partite ancora senza storico reale.
    # Cache persistente e limite per-esecuzione proteggono la quota del piano gratuito.
    try:
        from .engine_multimethod import get_stats_for_match
        missing=[r for r in base if not get_stats_for_match(r.get("home"),r.get("away"))]
        apikey=(config().get("api_football_key") or "").strip()
        maxreq=int(config().get("api_football_max_requests_per_run",40) or 40)
        ahist,ameta=ApiFootballHistoryCollector(apikey,maxreq).collect(missing)
        aadded=merge_stats_dict(ahist)
        status.append({"source":"GolBet API-Football Fallback",
                       "ok":bool(ameta.get("configured") and ameta.get("site_reached")),
                       "count":ameta.get("complete",0),
                       "details":f"MANCANTI={len(missing)} | MATCH={ameta.get('matched',0)} | 6 GARE COMPLETE={ameta.get('complete',0)} | AGGIUNTE={aadded} | RICHIESTE={ameta.get('requests',0)} | RESTANTI={ameta.get('remaining')}",
                       "error":ameta.get("error","")})
    except Exception as e:
        status.append({"source":"GolBet API-Football Fallback","ok":False,"count":0,"error":str(e)})

    # Legacy NOWGOALBET algorithm, fed by current AsianOdds OPEN/CURRENT prices.
    base=attach_nowgoalbet(base)
    # GOLBET usa solo storico reale (CSV o AutoHistory), mai STIMA MERCATO.
    base=attach_golbet(base)
    status.append({"source":"NowGoalBet","ok":True,"count":sum(1 for r in base if r.get("nowgoalbet_available")),
                   "details":"Algoritmo V.01 integrato; nessuno scraping del vecchio sito NowGoal"})
    status.append({"source":"GolBet","ok":any(r.get("golbet_available") for r in base),
                   "count":sum(1 for r in base if r.get("golbet_available")),
                   "details":"GOLBET v1.0: ultime 6 reali; propensione gol, rating, forma e rabbia. Nessun bonus Score iniziale."})
    base=apply_multisource_score(base)

    # AFootballReport: conferme indipendenti partita-per-partita
    try:
        afr_data,afr_meta=AFootballReportCollector().collect(base);base=attach_afr(base,afr_data)
        status.append({"source":"AFootballReport","ok":afr_meta.get("site_reached",False),"count":afr_meta.get("used",0),
                       "details":f"SITO={'OK' if afr_meta.get('site_reached') else 'NO'} | PAGINE={afr_meta.get('pages_read',0)} | "
                                 f"RIGHE LETTE={afr_meta.get('rows_read',0)} | PARTITE ABBINATE={afr_meta.get('matched',0)} | "
                                 f"DATI USATI={afr_meta.get('used',0)}",
                       "error":afr_meta.get("error","")})
    except Exception as e:
        for r in base:r["afootballreport"]=[]
        status.append({"source":"AFootballReport","ok":False,"count":0,"error":str(e)})
    # FootyStats: statistiche pubbliche reali di lega
    try:
        fs_data,fs_meta=FootyStatsCollector().collect(base);base=attach_footystats(base,fs_data)
        status.append({"source":"FootyStats","ok":fs_meta.get("site_reached",False),"count":fs_meta.get("used",0),
                       "details":f"SITO={'OK' if fs_meta.get('site_reached') else 'NO'} | PAGINE={fs_meta.get('pages_read',0)} | "
                                 f"RIGHE LETTE={fs_meta.get('rows_read',0)} | PARTITE ABBINATE={fs_meta.get('matched',0)} | "
                                 f"DATI USATI={fs_meta.get('used',0)} | DEBUG=Documenti/ANTONIOCAP.BET/DEBUG/DEBUG_FOOTYSTATS_371.json",
                       "error":fs_meta.get("error","")})
    except Exception as e:
        for r in base:r["footystats"]=None
        status.append({"source":"FootyStats","ok":False,"count":0,"error":str(e)})
    # SoccerStats247: statistiche pubbliche reali di competizione
    try:
        ss_data,ss_meta=SoccerStats247Collector().collect(base);base=attach_soccerstats247(base,ss_data)
        status.append({"source":"SoccerStats247","ok":ss_meta.get("site_reached",False),"count":ss_meta.get("used",0),
                       "details":f"SITO={'OK' if ss_meta.get('site_reached') else 'NO'} | INDICI={ss_meta.get('index_pages',0)} | "
                                 f"COMPETIZIONI LETTE={ss_meta.get('competition_links',0)} | LEGHE ABBINATE={ss_meta.get('matched',0)} | "
                                 f"DATI USATI={ss_meta.get('used',0)} | ERRORI={ss_meta.get('error_count',0)}",
                       "error":ss_meta.get("error","")[:240]})
    except Exception as e:
        for r in base:r["soccerstats247"]=None
        status.append({"source":"SoccerStats247","ok":False,"count":0,"error":str(e)})
    # Forebet: conferma statistica indipendente pubblica
    try:
        fb_data,fb_meta=ForebetCollector().collect(base);base=attach_forebet(base,fb_data)
        imported=bool(fb_meta.get("local_public_import"))
        status.append({"source":"Forebet","ok":imported,"count":fb_meta.get("used",0),
                       "state":"IMPORT PUBBLICO" if imported else "DA IMPORTARE",
                       "details":(f"CACHE LOCALE | LETTE={fb_meta.get('rows_read',0)} | ABBINATE={fb_meta.get('matched',0)} | "
                                  f"IMPORT={fb_meta.get('cache_created','--')}" if imported else
                                  "Salva normalmente una pagina Forebet dal browser e usa IMPORTA FOREBET HTML — nessun accesso 403"),
                       "error":""})
    except Exception as e:
        for r in base:r["forebet"]=None
        status.append({"source":"Forebet","ok":False,"count":0,"error":str(e)})
    # AUTO STATISTICHE: non sovrascrive mai un CSV importato dall'utente.
    # In assenza di storico usa una stima trasparente ricavata dai mercati pubblici.
    if stats_count()==0:
        auto_stats=build_market_stats(base)
        n_auto=set_stats_dict(auto_stats)
        status.append({"source":"AutoStatistiche","ok":bool(n_auto),"count":n_auto,
                       "details":f"STIMA MERCATO={n_auto} | Poisson/Value/Over1.5/Fissa/1T automatici | storico non inventato"})
    return apply_final_bets(apply_multimethod(base)),status
def evaluate_rows(rows):
    # collect_all already evaluates/enriches in V5.
    if rows and isinstance(rows[0],dict) and "score" in rows[0]: return apply_final_bets(rows)
    return sorted([evaluate(x) for x in rows],key=lambda x:(x["score"],x["completeness"]),reverse=True)
