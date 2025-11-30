# app/utils/crypto.py
import os
import hmac
import hashlib
import base64
import secrets
from datetime import datetime

ACTIVATION_SECRET = os.environ.get("ACTIVATION_SECRET", None)
if not ACTIVATION_SECRET:
    raise RuntimeError("ACTIVATION_SECRET env var must be set")

def generate_license_key():
    # human-friendly but random
    return secrets.token_urlsafe(16)

def sign_activation(license_key: str, device_id: str | None) -> str:
    payload = f"{license_key}|{device_id or ''}|{int(datetime.utcnow().timestamp())}"
    sig = hmac.new(ACTIVATION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload.encode() + b"~" + sig).decode()
    return token

def verify_activation_token(token: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        payload, sig = raw.rsplit(b"~", 1)
        expected = hmac.new(ACTIVATION_SECRET.encode(), payload, hashlib.sha256).digest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
