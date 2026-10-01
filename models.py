from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MatchData:
    home:str
    away:str
    date:str
    kickoff:str=""
    league:str=""
    source:str=""
    fav_spread_open:Optional[float]=None
    fav_spread_current:Optional[float]=None
    fav_price_open:Optional[float]=None
    fav_price_current:Optional[float]=None
    dog_price_open:Optional[float]=None
    dog_price_current:Optional[float]=None
    dog_price_open:Optional[float]=None
    ml_home_open:Optional[float]=None
    ml_draw_open:Optional[float]=None
    ml_away_open:Optional[float]=None
    ml_home_current:Optional[float]=None
    ml_draw_current:Optional[float]=None
    ml_away_current:Optional[float]=None
    btts_gg_open:Optional[float]=None
    btts_gg_current:Optional[float]=None
    btts_ng_open:Optional[float]=None
    btts_ng_current:Optional[float]=None
    total_open:Optional[float]=None
    total_current:Optional[float]=None
    over_price_open:Optional[float]=None
    over_price_current:Optional[float]=None
    under_price_open:Optional[float]=None
    under_price_current:Optional[float]=None
    spy_10bet_highest:bool=False
    spy_comeon_highest:bool=False
    spy_sportingbet_highest:bool=False
    spy_bwin_highest:bool=False
    spy_12bet_highest:bool=False
    h2h_support:Optional[bool]=None
    motivation_support:Optional[bool]=None
    raw_text:str=""
    def dict(self): return asdict(self)
