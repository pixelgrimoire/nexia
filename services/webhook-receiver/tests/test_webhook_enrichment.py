import hmac
import hashlib
import importlib.util
import os
from pathlib import Path

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
    credentials = Column(JSON)
    phone_number = Column(String)


class DummyRedis:
    def __init__(self):
        self.calls = []

    def xadd(self, stream, mapping):
        self.calls.append((stream, dict(mapping)))
        return None


@pytest.fixture
def client(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["WHATSAPP_APP_SECRET"] = "dev_secret"
    # reload DB
    import importlib
    import packages.common.db as common_db
    importlib.reload(common_db)

    # load app
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("webhook_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # create channels table and seed
    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        s.add(ChannelModel(id="ch1", org_id="o1", credentials={"phone_number_id": "pnid-xyz"}, phone_number="+123"))
        s.commit()
    finally:
        s.close()

    dummy = DummyRedis()
    main.redis = dummy
    with TestClient(main.app) as c:
        yield c, dummy


def sign(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return "sha256=" + mac


def test_webhook_enriches_with_org_and_channel(client):
    c, redis = client
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": "pnid-xyz",
                                "display_phone_number": "+123",
                            },
                            "messages": [
                                {"from": "1111", "id": "wamid.1", "timestamp": "1", "text": {"body": "hi"}},
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = bytes(__import__("json").dumps(payload), "utf-8")
    sig = sign("dev_secret", body)
    r = c.post("/api/webhooks/whatsapp", data=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200
    # two xadds expected: nf:inbox and nf:incoming
    assert len(redis.calls) == 2
    for stream, mapping in redis.calls:
        assert mapping.get("org_id") == "o1"
        assert mapping.get("channel_id") == "ch1"

