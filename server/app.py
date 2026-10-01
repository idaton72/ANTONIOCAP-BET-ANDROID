from datetime import date
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from backend.service import collect_all

app=FastAPI(title='ANTONIOCAP.BET 3.8.6 Android Bridge',version='0.6')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

@app.get('/health')
def health(): return {'ok':True,'engine':'3.8.6','bridge':'0.6'}

@app.get('/api/top50')
async def top50(day: str = Query(default_factory=lambda: date.today().isoformat())):
    rows,status=await collect_all(day)
    rows=sorted(rows,key=lambda r:int(r.get('multisource_score',r.get('final_score',r.get('score',0))) or 0),reverse=True)[:50]
    return {'day':day,'count':len(rows),'sources':status,'rows':rows}
