import re, unicodedata, requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
BASE="https://it.soccerstats247.com"
INDEXES=[BASE+"/competizioni/",BASE+"/"]
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}

def norm(s):
 s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
 return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())
def sim(a,b):
 a,b=norm(a),norm(b)
 if not a or not b:return 0
 if a==b:return 1
 if a in b or b in a:return .93
 return SequenceMatcher(None,a,b).ratio()
def split_league(x):
 x=str(x or "")
 if ":" in x:return [z.strip() for z in x.split(":",1)]
 return ["",x.strip()]
def links_from(html):
 soup=BeautifulSoup(html,"html.parser");out=[];seen=set()
 for a in soup.find_all("a",href=True):
  href=a["href"];name=" ".join(a.stripped_strings)
  if "/competizioni/" not in href or not name:continue
  if href.startswith("/"):href=BASE+href
  if not href.startswith(BASE+"/competizioni/") or href in seen:continue
  seen.add(href);out.append((name,href.split("?")[0]))
 return out
def parse_comp(html,url="",label=""):
 soup=BeautifulSoup(html,"html.parser");text=" ".join(soup.stripped_strings)
 d={"league":label,"url":url,"source":"SoccerStats247"}
 # Find visible Over/Under section and average team percentages.
 table=None
 for h in soup.find_all(["h2","h3","h4"]):
  if "over/under" in h.get_text(" ",strip=True).lower():
   table=h.find_next("table");break
 vals15=[];vals25=[];avg=[]
 if table:
  for tr in table.find_all("tr"):
   cells=[" ".join(x.stripped_strings) for x in tr.find_all(["td","th"])]
   p=[float(x.replace(",",".")) for x in re.findall(r"(\\d+(?:[.,]\\d+)?)\\s*%"," | ".join(cells))]
   if len(p)>=3:vals15.append(p[1]);vals25.append(p[2])
   for c in cells:
    try:
     v=float(c.replace(",","."))
     if 0<v<10:avg.append(v);break
    except:pass
 d["over15"]=round(sum(vals15)/len(vals15),1) if vals15 else None
 d["over25"]=round(sum(vals25)/len(vals25),1) if vals25 else None
 d["avg_goals"]=round(sum(avg)/len(avg),2) if avg else None
 d["has_over_under_section"]=bool(table)
 d["has_trends"]="Tendenze" in text;d["has_form"]="Forma" in text
 d["values_found"]=sum(v is not None for v in (d["over15"],d["over25"],d["avg_goals"]))
 return d

class SoccerStats247Collector:
 def collect(self,fixtures):
  s=requests.Session();s.headers.update(HEADERS)
  meta={"site_reached":False,"index_pages":0,"competition_links":0,"matched":0,"stats":0,"used":0}
  links=[];seen=set()
  for u in INDEXES:
   try:
    r=s.get(u,timeout=25);r.raise_for_status();meta["site_reached"]=True;meta["index_pages"]+=1
    for x in links_from(r.text):
     if x[1] not in seen:seen.add(x[1]);links.append(x)
   except Exception as e:meta.setdefault("errors",[]).append(str(e))
  meta["competition_links"]=len(links)
  # If index hides links, try no invented URLs: just leave source unavailable.
  targets=[]
  for f in fixtures:
   country,league=split_league(f.get("league",""))
   k=(country,league)
   if k not in targets:targets.append(k)
  out={}
  for country,league in targets:
   descriptor=norm(country+" "+league)
   ranked=[]
   for name,url in links:
    urltxt=url.replace("-"," ").replace("/"," ")
    sc=max(sim(descriptor,name+" "+urltxt), sim(league,name))
    if country and norm(country) in norm(urltxt):sc=min(1.0,sc+.12)
    ranked.append((sc,name,url))
   ranked.sort(reverse=True)
   if not ranked or ranked[0][0]<.58:continue
   sc,name,url=ranked[0];meta["matched"]+=1
   try:
    r=s.get(url,timeout=20);r.raise_for_status()
    d=parse_comp(r.text,url,f"{country}: {league}");d["matched_name"]=name;d["match_score"]=round(sc,3)
    out[norm(f"{country}: {league}")]=d
    if d["values_found"]:meta["stats"]+=1;meta["used"]+=d["values_found"]
   except Exception as e:meta.setdefault("errors",[]).append(f"{name}: {e}")
  meta["error_count"]=len(meta.get("errors",[]))
  meta["error"]=" | ".join(meta.get("errors",[])[:2])
  return out,meta
def attach(rows,data):
 for r in rows:r["soccerstats247"]=data.get(norm(r.get("league","")))
 return rows
