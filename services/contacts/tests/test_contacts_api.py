import os
from pathlib import Path
import sys
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base

TestBase = declarative_base()


class TestContact(TestBase):
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


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"
        root = Path(__file__).resolve().parents[3]
        sys.path.append(str(root))
        import services.contacts.app.main as main  # noqa: E402
        from packages.common.db import SessionLocal, engine  # noqa: E402

        main.Contact = TestContact
        TestBase.metadata.create_all(bind=engine)

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
        # Dispose the engine to close any pooled connections so the
        # temporary sqlite file can be removed on Windows.
        engine.dispose()


def test_crud_and_search(client: TestClient):
    payload = {
        "org_id": "o1",
        "name": "Ana",
        "phone": "123",
        "tags": ["vip"],
        "attributes": {"city": "CDMX"},
    }
    r = client.post("/api/contacts", json=payload)
    assert r.status_code == 201
    data = r.json()
    cid = data["id"]
    assert data["name"] == "Ana"

    r = client.get(f"/api/contacts/{cid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Ana"

    r = client.put(f"/api/contacts/{cid}", json={"name": "Ana Maria"})
    assert r.json()["name"] == "Ana Maria"

    r = client.get("/api/contacts")
    assert len(r.json()) == 1

    r = client.get("/api/contacts/search", params={"tags": "vip"})
    assert len(r.json()) == 1

    r = client.get(
        "/api/contacts/search", params={"attr_key": "city", "attr_value": "CDMX"}
    )
    assert len(r.json()) == 1

    r = client.delete(f"/api/contacts/{cid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get(f"/api/contacts/{cid}")
    assert r.status_code == 404
