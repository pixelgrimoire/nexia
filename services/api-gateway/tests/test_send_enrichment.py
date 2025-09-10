import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


class DummyRedis:
    def __init__(self):
        self.calls = []

    def xadd(self, stream, mapping):
        # Store a shallow copy to avoid mutation surprises
        self.calls.append((stream, dict(mapping)))
        return None


def make_token(role: str, org_id: str = "org1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def api() -> tuple[TestClient, DummyRedis]:
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["JWT_SECRET"] = "testsecret"
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    dummy = DummyRedis()
    main.redis = dummy
    with TestClient(main.app) as c:
        yield c, dummy


def test_enriches_send_with_org_and_user(api: tuple[TestClient, DummyRedis]):
    client, dummy = api
    token = make_token("admin", org_id="acme", sub="user-123")
    r = client.post(
        "/api/messages/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel_id": "c1", "to": "555", "type": "text", "text": "hi"},
    )
    assert r.status_code == 200
    assert r.json()["queued"] is True
    assert len(dummy.calls) == 1
    stream, mapping = dummy.calls[0]
    assert stream == "nf:outbox"
    assert mapping.get("org_id") == "acme"
    assert mapping.get("requested_by") == "user-123"
