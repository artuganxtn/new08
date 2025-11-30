# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")  # e.g. postgresql://postgres:...@...:5432/postgres

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var not set")

# Use SQLAlchemy engine (sync)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
