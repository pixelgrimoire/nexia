import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class DummyRedis:
    def xadd(self, *args, **kwargs):
        return None

    def xread(self, *args, **kwargs):
        return []


@pytest.fixture
def client(tmp_path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # create required tables
    from packages.common.db import engine
    from packages.common.models import Base

    # ensure only needed tables exist
    to_create = [
        Base.metadata.tables["organizations"],
        Base.metadata.tables["users"],
        Base.metadata.tables["refresh_tokens"],
    ]
    Base.metadata.create_all(bind=engine, tables=to_create)

    main.redis = DummyRedis()
    with TestClient(main.app) as c:
        yield c


def test_register_login_refresh_logout_flow(client: TestClient):
    # register
    r = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "Secret123", "org_name": "Acme"},
    )
    assert r.status_code == 200
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]
    assert access and refresh

    # use access in a protected route (send)
    r = client.post(
        "/api/messages/send",
        headers={"Authorization": f"Bearer {access}"},
        json={"channel_id": "c1", "to": "u", "type": "text", "text": "hi"},
    )
    assert r.status_code == 200

    # login again and ensure invalid creds are rejected
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "bad"})
    assert r.status_code == 401

    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "Secret123"})
    assert r.status_code == 200

    # refresh rotates
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != refresh

    # old refresh should be invalid after rotation
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401

    # logout revokes all tokens for user when called with access token
    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"}, json={})
    assert r.status_code == 200
