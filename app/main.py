# app/main.py
from fastapi import FastAPI
from app.routes import admin as admin_router
from app.routes import licenses as license_router
from app.models import Base
from app.database import engine

# create tables if not present (on startup)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PhoneTool License Server")

app.include_router(admin_router.router)
app.include_router(license_router.router)
