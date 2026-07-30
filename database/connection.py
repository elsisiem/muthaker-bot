import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL

_db_url = DATABASE_URL
if _db_url and _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_connect_args = {}
if "sqlite" in _db_url:
    _connect_args["check_same_thread"] = False

engine = create_engine(_db_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session():
    return SessionLocal()


def init_db():
    from .models import Base
    Base.metadata.create_all(bind=engine)