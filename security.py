
import os, sys, json, hashlib, subprocess, ctypes
from ctypes import wintypes

APP="ANTONIOCAP.BET"
PW_HASH="87e459288d48f6238acb527ed5799cb7afdba49585866b36f6ccd65fde51e125"

def password_ok(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()==PW_HASH

def _cmd(cmd):
    try:
        return subprocess.check_output(cmd,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),text=True,timeout=4).strip()
    except Exception:return ""

def machine_id():
    parts=[]
    if sys.platform=="win32":
        parts.append(_cmd(["wmic","csproduct","get","uuid"]))
        parts.append(_cmd(["wmic","bios","get","serialnumber"]))
        parts.append(_cmd(["wmic","baseboard","get","serialnumber"]))
        parts.append(os.environ.get("COMPUTERNAME",""))
    else:
        parts.append(os.uname().nodename if hasattr(os,"uname") else "unknown")
    clean="|".join(x for x in parts if x)
    return hashlib.sha256(clean.encode("utf-8","ignore")).hexdigest()

class DATA_BLOB(ctypes.Structure):
    _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_byte))]

def _blob(data):
    buf=ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte))),buf

def dpapi_encrypt(data):
    if sys.platform!="win32": return data
    ib,buf=_blob(data); ob=DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(ib),APP,None,None,None,0,ctypes.byref(ob)):
        raise OSError("DPAPI encrypt")
    try:return ctypes.string_at(ob.pbData,ob.cbData)
    finally:ctypes.windll.kernel32.LocalFree(ob.pbData)

def dpapi_decrypt(data):
    if sys.platform!="win32": return data
    ib,buf=_blob(data); ob=DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(ib),None,None,None,None,0,ctypes.byref(ob)):
        raise OSError("DPAPI decrypt")
    try:return ctypes.string_at(ob.pbData,ob.cbData)
    finally:ctypes.windll.kernel32.LocalFree(ob.pbData)

def token_path():
    d=os.path.join(os.environ.get("LOCALAPPDATA",os.path.expanduser("~")), "ANTONIOCAP.BET")
    os.makedirs(d,exist_ok=True)
    return os.path.join(d,"activation.dat")

def activate_local():
    payload=json.dumps({"app":APP,"machine":machine_id(),"v":1},sort_keys=True).encode()
    with open(token_path(),"wb") as f:f.write(dpapi_encrypt(payload))
    return True

def activation_ok():
    try:
        with open(token_path(),"rb") as f:data=dpapi_decrypt(f.read())
        obj=json.loads(data.decode())
        return obj.get("app")==APP and obj.get("machine")==machine_id() and obj.get("v")==1
    except Exception:return False
