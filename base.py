import re
def fnum(v):
    if v is None:return None
    m=re.search(r"[-+]?\d+(?:[.,]\d+)?",str(v))
    return float(m.group().replace(",",".")) if m else None
