# server/main.py
# FastAPI license server that uses Supabase REST API (service role key)
# Requirements: fastapi, uvicorn, requests, python-dotenv
# Run with: uvicorn server.main:app --host 0.0.0.0 --port 8000

import os
import secrets
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, List

import requests
from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel

# ---------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")  # e.g. https://xyzcompany.supabase.co
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # service_role key (keep secret)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "CHANGE_ME_ADMIN_TOKEN")
ACTIVATION_SECRET = os.environ.get("ACTIVATION_SECRET", "CHANGE_ME_ACTIVATION_SECRET")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")

REST_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

# Supabase table names (you will create them; SQL below)
LICENSES_TABLE = "licenses"
ACTIVATIONS_TABLE = "activations"

app = FastAPI(title="PhoneTool License Server (Supabase)")

# ---------------------------
# Pydantic models
class CheckRequest(BaseModel):
    license_key: str
    device_id: Optional[str] = None
    device_fingerprint: Optional[str] = None

class CheckResponse(BaseModel):
    valid: bool
    message: str
    license: Optional[dict] = None
    activation_token: Optional[str] = None

# ---------------------------
# Helpers: Supabase REST calls
def supabase_get_license_row(license_key: str) -> Optional[dict]:
    """Return license row or None"""
    url = f"{SUPABASE_URL}/rest/v1/{LICENSES_TABLE}"
    params = {"select": "*", "key": f"eq.{license_key}"}
    r = requests.get(url, headers=REST_HEADERS, params=params, timeout=8)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Supabase error")
    rows = r.json()
    return rows[0] if rows else None

def supabase_create_license_row(key: str, owner: str, plan: str, expires_at: Optional[str], max_activations: int) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{LICENSES_TABLE}"
    payload = {
        "key": key,
        "owner": owner,
        "plan": plan,
        "expires_at": expires_at,
        "max_activations": max_activations,
        "active": True,
        "created_at": datetime.utcnow().isoformat()
    }
    r = requests.post(url, headers=REST_HEADERS, json=payload, timeout=8)
    if r.status_code not in (201, 200):
        raise HTTPException(status_code=500, detail=f"Supabase create failed: {r.text}")
    return r.json()

def supabase_disable_license_row(license_key: str) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/{LICENSES_TABLE}"
    params = {"key": f"eq.{license_key}"}
    payload = {"active": False}
    r = requests.patch(url, headers=REST_HEADERS, params=params, json=payload, timeout=8)
    return r.status_code in (200, 204)

def supabase_list_licenses() -> List[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{LICENSES_TABLE}"
    params = {"select": "*"}
    r = requests.get(url, headers=REST_HEADERS, params=params, timeout=8)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Supabase error listing")
    return r.json()

def supabase_get_activations_for_license(license_id: int) -> List[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{ACTIVATIONS_TABLE}"
    params = {"select": "*", "license_id": f"eq.{license_id}"}
    r = requests.get(url, headers=REST_HEADERS, params=params, timeout=8)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Supabase error activations")
    return r.json()

def supabase_create_activation_row(license_id: int, device_id: str, device_fingerprint: Optional[str], ip: Optional[str]) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{ACTIVATIONS_TABLE}"
    payload = {
        "license_id": license_id,
        "device_id": device_id,
        "device_fingerprint": device_fingerprint,
        "ip": ip,
        "last_seen": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }
    r = requests.post(url, headers=REST_HEADERS, json=payload, timeout=8)
    if r.status_code not in (201,200):
        raise HTTPException(status_code=500, detail=f"Supabase create activation failed: {r.text}")
    return r.json()

def supabase_update_activation_last_seen(activation_id: int):
    url = f"{SUPABASE_URL}/rest/v1/{ACTIVATIONS_TABLE}"
    params = {"id": f"eq.{activation_id}"}
    payload = {"last_seen": datetime.utcnow().isoformat()}
    r = requests.patch(url, headers=REST_HEADERS, params=params, json=payload, timeout=8)
    return r.status_code in (200,204)

# ---------------------------
# Activation token signing (HMAC)
def sign_activation(license_key: str, device_id: Optional[str]) -> str:
    payload = f"{license_key}|{device_id if device_id else ''}|{int(datetime.utcnow().timestamp())}"
    sig = hmac.new(ACTIVATION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload.encode() + b"~" + sig).decode()
    return token

# ---------------------------
# Endpoints
@app.post("/api/check", response_model=CheckResponse)
def api_check(req: CheckRequest):
    # 1) lookup license
    lic = supabase_get_license_row(req.license_key)
    if not lic:
        return CheckResponse(valid=False, message="License not found")

    if not lic.get("active", True):
        return CheckResponse(valid=False, message="License disabled")

    expires_at = lic.get("expires_at")
    if expires_at:
        # ISO string stored in Supabase
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt < datetime.utcnow():
                return CheckResponse(valid=False, message="License expired")
        except Exception:
            pass

    license_id = lic["id"]

    # fetch activations for license
    activations = supabase_get_activations_for_license(license_id)

    # if device_id provided and exists, update last_seen and return OK
    existing = None
    if req.device_id:
        for a in activations:
            if a.get("device_id") == req.device_id:
                existing = a
                break

    if existing:
        supabase_update_activation_last_seen(existing["id"])
        token = sign_activation(lic["key"], req.device_id)
        return CheckResponse(valid=True, message="OK", license={
            "key": lic["key"],
            "owner": lic.get("owner"),
            "plan": lic.get("plan"),
            "expires_at": lic.get("expires_at")
        }, activation_token=token)

    # New activation: enforce max_activations
    max_act = lic.get("max_activations", 1) or 0  # 0 means unlimited
    if max_act > 0 and len(activations) >= max_act:
        return CheckResponse(valid=False, message="Activation limit reached")

    # create new activation row
    created = supabase_create_activation_row(license_id=license_id, device_id=req.device_id or "unknown", device_fingerprint=req.device_fingerprint, ip=None)
    token = sign_activation(lic["key"], req.device_id)
    return CheckResponse(valid=True, message="Activated", license={
        "key": lic["key"],
        "owner": lic.get("owner"),
        "plan": lic.get("plan"),
        "expires_at": lic.get("expires_at")
    }, activation_token=token)

# ---------------------------
# Admin endpoints (require ADMIN_TOKEN header)
def verify_admin(token: Optional[str]):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

@app.post("/admin/create_license")
def admin_create_license(owner: str, plan: str = "lifetime", duration_plan: str = "lifetime", max_activations: int = 1, x_admin_token: Optional[str] = Header(None)):
    """
    Create a new license.
      - plan: 'lifetime' or '1month'/'3months'/'6months' (for record)
      - duration_plan: same as plan (used to calculate expires_at)
    """
    verify_admin(x_admin_token)

    # compute expiry based on duration_plan
    expires_at = None
    if duration_plan == "1month":
        expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
    elif duration_plan == "3months":
        expires_at = (datetime.utcnow() + timedelta(days=90)).isoformat()
    elif duration_plan == "6months":
        expires_at = (datetime.utcnow() + timedelta(days=180)).isoformat()
    elif duration_plan == "lifetime":
        expires_at = None
    else:
        # unknown -> no expiry
        expires_at = None

    key = secrets.token_urlsafe(16)
    row = supabase_create_license_row(key=key, owner=owner, plan=plan, expires_at=expires_at, max_activations=max_activations)
    return {"license_key": row.get("key"), "owner": owner, "expires_at": expires_at}

@app.post("/admin/kill_license")
def admin_kill_license(license_key: str, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    ok = supabase_disable_license_row(license_key)
    if not ok:
        raise HTTPException(status_code=404, detail="License not found or could not disable")
    return {"ok": True}

@app.get("/admin/list_licenses")
def admin_list(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    licenses = supabase_list_licenses()
    # augment with activations
    out = []
    for lic in licenses:
        acts = supabase_get_activations_for_license(lic["id"])
        out.append({
            "key": lic["key"],
            "owner": lic.get("owner"),
            "plan": lic.get("plan"),
            "expires_at": lic.get("expires_at"),
            "active": lic.get("active"),
            "activations": [{"device_id": a.get("device_id"), "last_seen": a.get("last_seen")} for a in acts]
        })
    return {"licenses": out}

# ---------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
