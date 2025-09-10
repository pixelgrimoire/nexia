import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


class DummyRedis:
    def xadd(self, *args, **kwargs):
        return None


def make_token(role: str, org_id: str = "rateorg", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client() -> TestClient:
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["JWT_SECRET"] = "testsecret"
    os.environ["RATE_LIMIT_ENABLED"] = "true"
    os.environ["RATE_LIMIT_PER_MIN"] = "3"

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # reset limiter and stub redis
    main.reset_rate_limit()
    main.redis = DummyRedis()
    with TestClient(main.app) as c:
        yield c


def test_rate_limit_send_message(client: TestClient):
    token = make_token("admin", org_id="rateorg")
    payload = {"channel_id": "c1", "to": "u", "type": "text", "text": "hi"}
    for i in range(3):
        r = client.post("/api/messages/send", headers={"Authorization": f"Bearer {token}"}, json=payload)
        assert r.status_code == 200
    r = client.post("/api/messages/send", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert r.status_code == 429

