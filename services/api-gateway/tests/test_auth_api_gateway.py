import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


class DummyRedis:
    def xadd(self, *args, **kwargs):
        return None

    def xread(self, *args, **kwargs):
        return []


def make_token(role: str) -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": "u1", "role": role}, secret, algorithm="HS256")


@pytest.fixture
def client() -> TestClient:
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["JWT_SECRET"] = "testsecret"
    root = Path(__file__).resolve().parents[2]
    module_path = root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    main.redis = DummyRedis()
    with TestClient(main.app) as c:
        yield c


def test_missing_token(client: TestClient):
    r = client.post(
        "/api/messages/send",
        json={"channel_id": "c1", "to": "u", "type": "text", "text": "hi"},
    )
    assert r.status_code == 401


def test_forbidden_role(client: TestClient):
    token = make_token("viewer")
    r = client.post(
        "/api/messages/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel_id": "c1", "to": "u", "type": "text", "text": "hi"},
    )
    assert r.status_code == 403


def test_allowed_role(client: TestClient):
    token = make_token("admin")
    r = client.post(
        "/api/messages/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel_id": "c1", "to": "u", "type": "text", "text": "hi"},
    )
    assert r.status_code == 200
    assert r.json()["queued"] is True

