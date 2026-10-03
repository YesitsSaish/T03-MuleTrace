# src/upifraud/auth.py
"""Authentication utilities for Mule‑Hunt.

Provides a very lightweight username/password login backed by a separate SQLite
database (``auth.db``). Passwords are stored as SHA‑256 hashes with a per‑user
salt. The module exposes a FastAPI ``APIRouter`` with ``/auth/register`` and
``/auth/login`` endpoints. Upon successful login a signed JSON‑Web‑Token (JWT)
is returned; the token can be used by the front‑end for subsequent API calls.

Only the minimal functionality required for a demo UI is implemented – no
refresh‑token handling, password reset flow, or account lockout.
"""

from __future__ import annotations

import os
import hashlib
import secrets
import datetime as dt
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine,
    Table,
    Column,
    Integer,
    String,
    MetaData,
    select,
    insert,
)
import jwt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_DB = Path(__file__).resolve().parent / "auth.db"
JWT_SECRET = os.getenv("MULE_HUNT_JWT_SECRET", "dev-secret-key")
JWT_ALG = "HS256"
TOKEN_EXPIRE_MINUTES = 60

# ---------------------------------------------------------------------------
# Database setup – a tiny SQLite file with a single ``users`` table.
# ---------------------------------------------------------------------------
engine = create_engine(f"sqlite:///{DEFAULT_DB}", future=True, echo=False)
metadata = MetaData()
users_tbl = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, unique=True, nullable=False),
    Column("salt", String, nullable=False),
    Column("password_hash", String, nullable=False),
)
metadata.create_all(engine)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt: str) -> str:
    """Return a hex SHA‑256 hash of ``salt + password``.

    Using a per‑user salt prevents pre‑computed rainbow‑table attacks while still
    keeping the implementation trivial for the demo.
    """
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def _create_user(username: str, password: str) -> None:
    with engine.begin() as conn:
        exists = conn.execute(select(users_tbl.c.id).where(users_tbl.c.username == username)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username already taken")
        salt = secrets.token_hex(16)
        pwd_hash = _hash_password(password, salt)
        conn.execute(insert(users_tbl).values(username=username, salt=salt, password_hash=pwd_hash))

def _verify_user(username: str, password: str) -> bool:
    with engine.begin() as conn:
        row = conn.execute(select(users_tbl.c.salt, users_tbl.c.password_hash).where(users_tbl.c.username == username)).first()
        if not row:
            return False
        salt, stored_hash = row
        return _hash_password(password, salt) == stored_hash

def _create_access_token(data: dict, expires_delta: dt.timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = dt.datetime.utcnow() + (expires_delta or dt.timedelta(minutes=TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=6)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterPayload):
    """Create a new user and return a JWT.

    For simplicity the endpoint immediately logs the user in after registration.
    """
    _create_user(payload.username, payload.password)
    token = _create_access_token({"sub": payload.username})
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    """Validate credentials and return a JWT.

    ``OAuth2PasswordRequestForm`` expects ``username`` and ``password`` fields in a
    standard ``application/x-www-form-urlencoded`` request.
    """
    if not _verify_user(form.username, form.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_access_token({"sub": form.username})
    return TokenResponse(access_token=token)

# ---------------------------------------------------------------------------
# Simple login page (served as a static file)
# ---------------------------------------------------------------------------
# The HTML file lives under ``src/upifraud/frontend/login.html``. It posts to the
# ``/auth/login`` endpoint using JavaScript ``fetch`` and stores the JWT in
# ``localStorage`` for later use. The static files mount in the main FastAPI app
# (see ``api.create_app``) will expose it at ``/login.html``.

# End of auth.py
