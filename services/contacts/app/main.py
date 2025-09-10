import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import uuid4

from sqlalchemy.orm import Session

from packages.common.db import SessionLocal, engine
from packages.common.models import Contact

from contextlib import asynccontextmanager

# Prepare a Pydantic v2 model_config if available; keep None for v1.
try:
    from pydantic import ConfigDict  # type: ignore

    MODEL_CONFIG = ConfigDict(from_attributes=True)
except Exception:
    MODEL_CONFIG = None


SKIP_DDL = os.getenv("CONTACTS_SKIP_DDL", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the contacts table exists before the app accepts requests (unless skipped).
    if not SKIP_DDL:
        Contact.__table__.create(bind=engine, checkfirst=True)
    yield


# Create the FastAPI app with a lifespan handler instead of on_event
app = FastAPI(title="NexIA Contacts", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
REQUIRE_AUTH = os.getenv("CONTACTS_REQUIRE_AUTH", "false").lower() == "true"


def decode_bearer_token(request: Request) -> dict | None:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        if REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="invalid-token")
        return None


def current_user_optional(request: Request):
    user = decode_bearer_token(request)
    if REQUIRE_AUTH and not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


# Pydantic schemas ---------------------------------------------------------
class ContactBase(BaseModel):
    org_id: str
    wa_id: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    consent: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None


class ContactCreate(ContactBase):
    id: Optional[str] = None


class ContactUpdate(BaseModel):
    wa_id: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    consent: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None


class ContactOut(ContactBase):
    id: str

    # Support both Pydantic v2 (model_config / ConfigDict) and v1 (Config.orm_mode)
    if MODEL_CONFIG is not None:
        model_config = MODEL_CONFIG
    else:
        class Config:  # type: ignore
            orm_mode = True


# Routes -------------------------------------------------------------------
@app.post("/api/contacts", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db), user: dict | None = Depends(current_user_optional)):
    cid = payload.id or str(uuid4())
    # Enforce org_id from token when available; prevent cross-org writes
    if user:
        token_org = user.get("org_id")
        if payload.org_id and payload.org_id != token_org:
            raise HTTPException(status_code=403, detail="forbidden: org mismatch")
        if not payload.org_id:
            payload.org_id = token_org
    contact = Contact(
        id=cid,
        org_id=payload.org_id,
        wa_id=payload.wa_id,
        phone=payload.phone,
        name=payload.name,
        attributes=payload.attributes,
        tags=payload.tags,
        consent=payload.consent,
        locale=payload.locale,
        timezone=payload.timezone,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@app.get("/api/contacts", response_model=List[ContactOut])
def list_contacts(db: Session = Depends(get_db), user: dict | None = Depends(current_user_optional)):
    q = db.query(Contact)
    if user:
        q = q.filter(Contact.org_id == user.get("org_id"))
    return q.all()


@app.get("/api/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, db: Session = Depends(get_db), user: dict | None = Depends(current_user_optional)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    if user and getattr(contact, "org_id", None) != user.get("org_id"):
        raise HTTPException(status_code=404, detail="contact not found")
    return contact


@app.put("/api/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: str, payload: ContactUpdate, db: Session = Depends(get_db), user: dict | None = Depends(current_user_optional)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    if user and getattr(contact, "org_id", None) != user.get("org_id"):
        raise HTTPException(status_code=404, detail="contact not found")
    # Use model_dump when running Pydantic v2, fall back to dict() for v1.
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(exclude_unset=True)
    else:
        data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str, db: Session = Depends(get_db), user: dict | None = Depends(current_user_optional)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    if user and getattr(contact, "org_id", None) != user.get("org_id"):
        raise HTTPException(status_code=404, detail="contact not found")
    db.delete(contact)
    db.commit()
    return {"ok": True}


@app.get("/api/contacts/search", response_model=List[ContactOut])
def search_contacts(
    tags: Optional[List[str]] = Query(None),
    attr_key: Optional[str] = None,
    attr_value: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict | None = Depends(current_user_optional),
):
    q = db.query(Contact)
    if user:
        q = q.filter(Contact.org_id == user.get("org_id"))
    contacts = q.all()
    if tags:
        contacts = [c for c in contacts if set(tags).issubset(set(c.tags or []))]
    if attr_key and attr_value:
        contacts = [
            c for c in contacts
            if c.attributes and str(c.attributes.get(attr_key)) == attr_value
        ]
    return contacts


@app.get("/healthz")
async def healthz():
    return {"ok": True}
