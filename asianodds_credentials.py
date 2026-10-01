SERVICE="ANTONIOCAP.BET.AsianOdds"
USER_KEY="username"

def _keyring():
    import keyring
    return keyring

def save_credentials(username,password):
    k=_keyring()
    k.set_password(SERVICE,USER_KEY,(username or "").strip())
    k.set_password(SERVICE,(username or "").strip(),password or "")

def load_credentials():
    try:
        k=_keyring()
        u=k.get_password(SERVICE,USER_KEY)
        if not u:return None,None
        return u,k.get_password(SERVICE,u)
    except Exception:
        return None,None

def delete_credentials():
    try:
        k=_keyring()
        u=k.get_password(SERVICE,USER_KEY)
        if u:
            try:k.delete_password(SERVICE,u)
            except Exception:pass
        try:k.delete_password(SERVICE,USER_KEY)
        except Exception:pass
    except Exception:pass
