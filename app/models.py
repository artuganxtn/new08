# app/models.py
from sqlalchemy import Column, Integer, Text, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    duration_days = Column(Integer, nullable=True)  # null => lifetime
    price = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(Text, unique=True, nullable=False, index=True)
    owner = Column(Text, nullable=True)
    plan = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    max_activations = Column(Integer, default=1)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Activation(Base):
    __tablename__ = "activations"
    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(Integer, nullable=False)  # FK not declared for portability
    device_id = Column(Text, nullable=True)
    device_fingerprint = Column(Text, nullable=True)
    ip = Column(Text, nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
