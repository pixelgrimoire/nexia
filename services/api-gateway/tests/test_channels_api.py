import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base


DBBase = declarative_base()


class ChannelModel(DBBase):
    __tablename__ = "channels"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    type = Column(String)
    mode = Column(String)
    status = Column(String)
    credentials = Column(JSON)
    phone_number = Column(String)


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client(tmp_path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # inject sqlite-friendly Channel model
    main.Channel = ChannelModel
    from packages.common.db import engine
    DBBase.metadata.create_all(bind=engine)

    with TestClient(main.app) as c:
        yield c


def test_channel_crud_and_uniqueness(client: TestClient):
    token_o1 = make_token("admin", org_id="o1")
    token_o2 = make_token("admin", org_id="o2")

    # Create channel in org o1
    r = client.post(
        "/api/channels",
        headers={"Authorization": f"Bearer {token_o1}"},
        json={"type": "whatsapp", "mode": "cloud", "phone_number": "+111", "credentials": {"phone_number_id": "pnid-1"}},
    )
    assert r.status_code == 200
    ch = r.json()

    # Duplicate phone number in same org should fail
    r = client.post(
        "/api/channels",
        headers={"Authorization": f"Bearer {token_o1}"},
        json={"type": "whatsapp", "mode": "cloud", "phone_number": "+111"},
    )
    assert r.status_code == 409

    # Same phone number in different org ok
    r = client.post(
        "/api/channels",
        headers={"Authorization": f"Bearer {token_o2}"},
        json={"type": "whatsapp", "mode": "cloud", "phone_number": "+111"},
    )
    assert r.status_code == 200

    # Duplicate phone_number_id within same org should fail
    r = client.post(
        "/api/channels",
        headers={"Authorization": f"Bearer {token_o1}"},
        json={"type": "whatsapp", "mode": "cloud", "credentials": {"phone_number_id": "pnid-1"}},
    )
    assert r.status_code == 409

    # List returns only org's channels
    r = client.get("/api/channels", headers={"Authorization": f"Bearer {token_o1}"})
    assert r.status_code == 200
    items = r.json()
    assert all(it["org_id"] == "o1" for it in items)

    # Update with conflicting phone_number should raise 409
    # First, create another channel in o1 with different number
    r2 = client.post(
        "/api/channels",
        headers={"Authorization": f"Bearer {token_o1}"},
        json={"type": "whatsapp", "mode": "cloud", "phone_number": "+222"},
    )
    assert r2.status_code == 200
    ch2 = r2.json()
    r3 = client.put(
        f"/api/channels/{ch2['id']}",
        headers={"Authorization": f"Bearer {token_o1}"},
        json={"phone_number": "+111"},
    )
    assert r3.status_code == 409

