# cli/create_license_cli.py
# Local CLI to create and deactivate licenses (uses DB directly)
import os
import argparse
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import License
from app.utils.crypto import generate_license_key

def create_license(owner: str, plan: str, duration_plan: str, max_activations: int):
    expiry = None
    now = datetime.utcnow()
    if duration_plan == "1month":
        expiry = now + timedelta(days=30)
    elif duration_plan == "3months":
        expiry = now + timedelta(days=90)
    elif duration_plan == "6months":
        expiry = now + timedelta(days=180)
    elif duration_plan == "lifetime":
        expiry = None
    else:
        raise ValueError("Unknown duration_plan")

    key = generate_license_key()
    db = SessionLocal()
    try:
        lic = License(license_key=key, owner=owner, plan=plan, expires_at=expiry, max_activations=max_activations, active=True)
        db.add(lic)
        db.commit()
        db.refresh(lic)
        print("License created:", lic.license_key)
        print("Expires at:", lic.expires_at)
    finally:
        db.close()

def deactivate_license(license_key: str):
    db = SessionLocal()
    try:
        lic = db.query(License).filter(License.license_key == license_key).first()
        if not lic:
            print("License not found")
            return
        lic.active = False
        db.add(lic)
        db.commit()
        print("License deactivated:", license_key)
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "deactivate"])
    parser.add_argument("--owner", help="Owner name/email")
    parser.add_argument("--plan", default="manual", help="Plan name")
    parser.add_argument("--duration", default="lifetime", help="duration_plan: lifetime/1month/3months/6months")
    parser.add_argument("--max", type=int, default=1, help="Max activations (0 = unlimited)")
    parser.add_argument("--key", help="License key (for deactivate)")

    args = parser.parse_args()

    if args.action == "create":
        if not args.owner:
            print("owner required for create")
            return
        create_license(owner=args.owner, plan=args.plan, duration_plan=args.duration, max_activations=args.max)
    else:
        if not args.key:
            print("key required for deactivate")
            return
        deactivate_license(args.key)

if __name__ == "__main__":
    main()
