
import os, json, base64
from pathlib import Path
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from backend.security import machine_id

PUBLIC_KEY_B64="xM9tPigw+2SAT595YJC37PBwJpvD8PEZWNrpYYlKZys="
APP_ID="ANTONIOCAP.BET"
LICENSE_FILE="ANTONIOCAP.lic"

def _pub():
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))

def license_path():
    # Prefer same folder as executable/app; fallback LOCALAPPDATA
    candidates=[]
    try:
        import sys
        base=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]
        candidates.append(base/LICENSE_FILE)
    except Exception:
        pass
    local=Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "ANTONIOCAP.BET" / LICENSE_FILE
    candidates.append(local)
    for p in candidates:
        if p.exists(): return p
    return candidates[-1]

def parse_license_bytes(data:bytes):
    obj=json.loads(data.decode("utf-8"))
    payload=obj.get("payload")
    sig_b64=obj.get("signature")
    if not isinstance(payload,dict) or not sig_b64:
        return False,"Formato licenza non valido",None
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":")).encode("utf-8")
    try:
        _pub().verify(base64.b64decode(sig_b64),canonical)
    except Exception:
        return False,"Firma licenza non valida",None
    if payload.get("app")!=APP_ID:
        return False,"Licenza per un'altra applicazione",payload
    if payload.get("machine_id")!=machine_id():
        return False,"Licenza non valida per questo PC",payload
    exp=payload.get("expires")
    if exp:
        try:
            dt=datetime.fromisoformat(exp.replace("Z","+00:00"))
            if dt < datetime.now(timezone.utc):
                return False,"Licenza scaduta",payload
        except Exception:
            return False,"Data scadenza non valida",payload
    return True,"Licenza valida",payload

def validate_installed_license():
    p=license_path()
    if not p.exists():
        return False,"Licenza non trovata",None
    try:
        return parse_license_bytes(p.read_bytes())
    except Exception as e:
        return False,f"Errore lettura licenza: {e}",None

def install_license(source_path):
    src=Path(source_path)
    ok,msg,payload=parse_license_bytes(src.read_bytes())
    if not ok: return False,msg,None
    dst=Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "ANTONIOCAP.BET" / LICENSE_FILE
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return True,"Licenza installata",payload
