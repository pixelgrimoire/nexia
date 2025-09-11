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

    # Monkeypatch channel model
    main.Channel = ChannelModel  # type: ignore
    from packages.common.db import engine, SessionLocal

    DBBase.metadata.create_all(bind=engine)

    # seed a channel with phone_number_id
    s = SessionLocal()
    try:
        s.add(ChannelModel(id="ch1", org_id="o1", type="whatsapp", mode="cloud", status="active", phone_number="+1000", credentials={"phone_number_id": "pn1"}))
        s.commit()
    finally:
        s.close()

    # Patch mgw status fetcher to return pn1
    def fake_fetch():
        return {"workers": {"send_worker": {"fake": True, "has_token": False, "phone_id": "pn1"}}}

    main._fetch_mgw_status = fake_fetch  # type: ignore

    with TestClient(main.app) as c:
        yield c


def test_verify_channel_ok(client: TestClient):
    token = make_token("admin", org_id="o1")
    r = client.post("/api/channels/ch1/verify", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["match"] is True
    assert data.get("fake") is True

