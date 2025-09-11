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


class TemplateModel(DBBase):
    __tablename__ = "templates"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    name = Column(String)
    language = Column(String)
    category = Column(String)
    body = Column(String)
    variables = Column(JSON)
    status = Column(String)


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


class DummyRedis:
    def xadd(self, *args, **kwargs):
        return None


@pytest.fixture
def client(tmp_path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # Swap DBTemplate to sqlite-friendly model and create table
    main.DBTemplate = TemplateModel  # type: ignore
    from packages.common.db import engine, SessionLocal

    DBBase.metadata.create_all(bind=engine)

    main.redis = DummyRedis()
    with TestClient(main.app) as c:
        yield c


def test_template_must_be_approved(client: TestClient):
    token = make_token("admin", org_id="o1")
    headers = {"Authorization": f"Bearer {token}"}

    # Fails when template not approved / not present
    r = client.post(
        "/api/messages/send",
        headers=headers,
        json={
            "channel_id": "c1",
            "to": "+1",
            "type": "template",
            "template": {"name": "welcome", "language": {"code": "es"}},
        },
    )
    assert r.status_code == 422

    # Insert approved template and try again
    from packages.common.db import SessionLocal
    s = SessionLocal()
    try:
        s.add(TemplateModel(id="t1", org_id="o1", name="welcome", language="es", status="approved"))
        s.commit()
    finally:
        s.close()

    r2 = client.post(
        "/api/messages/send",
        headers=headers,
        json={
            "channel_id": "c1",
            "to": "+1",
            "type": "template",
            "template": {"name": "welcome", "language": {"code": "es"}},
        },
    )
    assert r2.status_code == 200
    assert r2.json().get("queued") is True

