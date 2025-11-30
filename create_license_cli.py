from server.main import engine, License
from sqlmodel import Session
from datetime import datetime, timedelta
import secrets


if __name__ == "__main__":
owner = input("Owner name/email: ")
plan = input("Plan (single/pro): ") or "single"
days = input("Expires in how many days? (blank for none): ")
max_act = int(input("Max activations (0 for unlimited): "))


expires_at = None
if days:
expires_at = datetime.utcnow() + timedelta(days=int(days))


key = secrets.token_urlsafe(16)


lic = License(key=key, owner=owner, plan=plan, expires_at=expires_at, max_activations=max_act)
with Session(engine) as s:
s.add(lic)
s.commit()
print("Created license:", key)