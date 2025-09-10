import os
from pathlib import Path
import sys
import tempfile
from typing import Generator

import pytest
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import Column, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base

DBBase = declarative_base()


class ContactModel(DBBase):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    wa_id = Column(String)
    phone = Column(String)
    name = Column(String)
    attributes = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    consent = Column(String)
    locale = Column(String)
    timezone = Column(String)


def make_token(org_id: str, role: str = "admin", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"
        os.environ["JWT_SECRET"] = "testsecret"
        root = Path(__file__).resolve().parents[3]
        sys.path.append(str(root))
        # Reload DB module to ensure it picks up DATABASE_URL
        import importlib
        import packages.common.db as common_db  # noqa: E402
        importlib.reload(common_db)
        # Avoid DDL in app lifespan; we create tables explicitly here
        os.environ["CONTACTS_SKIP_DDL"] = "true"
        import services.contacts.app.main as main  # noqa: E402
        importlib.reload(main)
        from packages.common.db import SessionLocal, engine  # noqa: E402

        main.Contact = ContactModel
        DBBase.metadata.create_all(bind=engine)

        def override_get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[main.get_db] = override_get_db
        with TestClient(main.app) as c:
            yield c
        main.app.dependency_overrides.clear()
        engine.dispose()


def test_tenancy_enforced_on_list(client: TestClient):
    # Create two contacts under different orgs using unauthenticated calls (legacy path)
    r = client.post("/api/contacts", json={"org_id": "o1", "name": "Ana"})
    assert r.status_code == 201
    r = client.post("/api/contacts", json={"org_id": "o2", "name": "Beto"})
    assert r.status_code == 201

    # List with token for o1 only returns Ana
    token = make_token("o1")
    r = client.get("/api/contacts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names == ["Ana"], names

    # Cross-org fetch by id returns 404
    all_contacts = client.get("/api/contacts").json()
    cid_o2 = [c for c in all_contacts if c["org_id"] == "o2"][0]["id"]
    r = client.get(f"/api/contacts/{cid_o2}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
