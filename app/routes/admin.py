# app/routes/admin.py
from fastapi import APIRouter, HTTPException, Header, status, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import os

from app.database import SessionLocal
from app.models import License, Plan, Activation, Base
from app.utils.crypto import generate_license_key

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", None)
if not ADMIN_TOKEN:
    raise RuntimeError("ADMIN_TOKEN env var must be set")

router = APIRouter(prefix="/admin", tags=["admin"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_admin(token: str | None):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

@router.post("/create_license")
def create_license(owner: str, duration_plan: str = "lifetime", max_activations: int = 1, x_admin_token: str | None = Header(None), db: Session = Depends(get_db)):
    verify_admin(x_admin_token)
    # compute expiry
    expires_at = None
    if duration_plan == "1month":
        expires_at = datetime.utcnow() + timedelta(days=30)
    elif duration_plan == "3months":
        expires_at = datetime.utcnow() + timedelta(days=90)
    elif duration_plan == "6months":
        expires_at = datetime.utcnow() + timedelta(days=180)
    elif duration_plan == "lifetime":
        expires_at = None
    else:
        raise HTTPException(status_code=400, detail="Unknown duration_plan")

    key = generate_license_key()
    lic = License(
        license_key=key,
        owner=owner,
        plan=duration_plan,
        expires_at=expires_at,
        max_activations=max_activations,
        active=True
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return {"license_key": lic.license_key, "expires_at": lic.expires_at.isoformat() if lic.expires_at else None, "max_activations": lic.max_activations}

@router.post("/kill_license")
def kill_license(license_key: str, x_admin_token: str | None = Header(None), db: Session = Depends(get_db)):
    verify_admin(x_admin_token)
    lic = db.query(License).filter(License.license_key == license_key).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    lic.active = False
    db.add(lic)
    db.commit()
    return {"ok": True}

@router.get("/list_licenses")
def list_licenses(x_admin_token: str | None = Header(None), db: Session = Depends(get_db)):
    verify_admin(x_admin_token)
    items = db.query(License).all()
    out = []
    for lic in items:
        # get activations count
        act_count = db.query(Activation).filter(Activation.license_id == lic.id).count()
        out.append({
            "license_key": lic.license_key,
            "owner": lic.owner,
            "plan": lic.plan,
            "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
            "active": lic.active,
            "activations": act_count
        })
    return {"licenses": out}
