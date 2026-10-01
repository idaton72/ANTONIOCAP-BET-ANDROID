import csv,io
from .base import fnum
from ..models import MatchData
def import_csv_bytes(data,default_date):
    text=data.decode("utf-8-sig",errors="ignore"); delim=";" if text[:5000].count(";")>text[:5000].count(",") else ","
    r=csv.DictReader(io.StringIO(text),delimiter=delim);out=[]
    for x in r:
        low={str(k).strip().lower():v for k,v in x.items()}
        home=(low.get("home") or low.get("casa") or "").strip();away=(low.get("away") or low.get("trasferta") or "").strip()
        if not home or not away:continue
        out.append(MatchData(home,away,(low.get("date") or default_date).strip(),
            source="CSV import",fav_spread_open=fnum(low.get("fav_spread_open") or low.get("spread_open")),
            fav_spread_current=fnum(low.get("fav_spread_current") or low.get("spread_current")),
            fav_price_open=fnum(low.get("fav_price_open")),fav_price_current=fnum(low.get("fav_price_current")),
            dog_price_current=fnum(low.get("dog_price_current")),total_open=fnum(low.get("total_open")),
            total_current=fnum(low.get("total_current")),over_price_open=fnum(low.get("over_price_open")),
            over_price_current=fnum(low.get("over_price_current"))))
    return out
