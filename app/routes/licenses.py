# app/routes/licenses.py
from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import SessionLocal
from app.models import License, Activation
from app.utils.crypto import sign_activation, verify_activation_token

router = APIRouter(prefix="/license", tags=["license"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ActivateRequest:
    # used only by type hints, request parsing in FastAPI will parse body dict
    pass

@router.post("/activate")
def activate_license(payload: dict, db: Session = Depends(get_db), request: Request = None):
    """
    Expected JSON body:
    {
      "license_key": "...",
      "device_id": "...",
      "device_fingerprint": "..."
    }
    """
    license_key = payload.get("license_key")
    device_id = payload.get("device_id")
    device_fingerprint = payload.get("device_fingerprint")

    if not license_key:
        raise HTTPException(status_code=400, detail="license_key required")

    lic = db.query(License).filter(License.license_key == license_key).first()
    if not lic:
        return {"valid": False, "message": "License not found"}

    if not lic.active:
        return {"valid": False, "message": "License disabled"}

    # expiry check
    if lic.expires_at and lic.expires_at < datetime.utcnow():
        return {"valid": False, "message": "License expired"}

    # existing activation by device
    existing = None
    if device_id:
        existing = db.query(Activation).filter(Activation.license_id == lic.id, Activation.device_id == device_id).first()

    if existing:
        existing.last_seen = datetime.utcnow()
        db.add(existing)
        db.commit()
        token = sign_activation(lic.license_key, device_id)
        return {"valid": True, "message": "OK", "activation_token": token, "license": {"key": lic.license_key, "owner": lic.owner, "plan": lic.plan, "expires_at": lic.expires_at.isoformat() if lic.expires_at else None}}

    # enforce max activations
    act_count = db.query(Activation).filter(Activation.license_id == lic.id).count()
    max_act = lic.max_activations or 0
    if max_act > 0 and act_count >= max_act:
        return {"valid": False, "message": "Activation limit reached"}

    # create activation
    ip = None
    if request:
        ip = request.client.host if request.client else None

    a = Activation(license_id=lic.id, device_id=device_id or "unknown", device_fingerprint=device_fingerprint, ip=ip, last_seen=datetime.utcnow())
    db.add(a)
    db.commit()
    db.refresh(a)

    token = sign_activation(lic.license_key, device_id)
    return {"valid": True, "message": "Activated", "activation_token": token, "license": {"key": lic.license_key, "owner": lic.owner, "plan": lic.plan, "expires_at": lic.expires_at.isoformat() if lic.expires_at else None}}

@router.post("/verify_token")
def verify_token(payload: dict):
    token = payload.get("activation_token")
    if not token:
        raise HTTPException(status_code=400, detail="activation_token required")
    ok = verify_activation_token(token)
    return {"valid": ok}
