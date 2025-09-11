import base64
import hmac
import hashlib
import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class DummyRedis:
    def __init__(self):
        self.calls = []

    def xadd(self, stream, mapping):
        self.calls.append((stream, dict(mapping)))
        return None


@pytest.fixture
def client() -> TestClient:
    os.environ["WHATSAPP_APP_SECRET"] = "dev_secret"
    os.environ["WHATSAPP_VERIFY_TOKEN"] = "verify"
    os.environ["DATABASE_URL"] = "sqlite://"

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("webhook_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    dummy = DummyRedis()
    main.redis = dummy
    with TestClient(main.app) as c:
        yield c, dummy


def _sig(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_invalid_signature_rejected(client):
    c, _ = client
    body = b"{}"
    r = c.post("/api/webhooks/whatsapp", data=body, headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 403


def test_valid_signature_enqueues_streams(client):
    c, dummy = client
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "1", "text": {"body": "hola"}}]}}]}]}
    import json

    body = json.dumps(payload).encode()
    sig = _sig(b"dev_secret", body)
    r = c.post("/api/webhooks/whatsapp", data=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200
    streams = [s for s, _ in dummy.calls]
    assert "nf:inbox" in streams and "nf:incoming" in streams
