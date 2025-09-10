from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import uuid4

from sqlalchemy.orm import Session

from packages.common.db import SessionLocal, engine
from packages.common.models import Contact

app = FastAPI(title="NexIA Contacts")


# Create tables on startup (no-op if already exist)
@app.on_event("startup")
def on_startup() -> None:
    Contact.__table__.create(bind=engine, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

    class Config:
        orm_mode = True


# Routes -------------------------------------------------------------------
@app.post("/api/contacts", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    cid = payload.id or str(uuid4())
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
def list_contacts(db: Session = Depends(get_db)):
    return db.query(Contact).all()


@app.get("/api/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    return contact


@app.put("/api/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: str, payload: ContactUpdate, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
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
):
    contacts = db.query(Contact).all()
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
