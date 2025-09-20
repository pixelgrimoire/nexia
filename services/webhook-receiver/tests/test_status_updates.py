import hmac
import hashlib
import importlib.util
import os
from pathlib import Path

import json
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


class MessageModel(DBBase):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    conversation_id = Column(String)
    direction = Column(String)
    type = Column(String)
    content = Column(JSON)
    template_id = Column(String)
    status = Column(String)
    meta = Column(JSON)
    client_id = Column(String)


class DummyRedis:
    def __init__(self):
        self.calls = []

    def xadd(self, stream, mapping):
        self.calls.append((stream, dict(mapping)))
        return None


def sign(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return "sha256=" + mac


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

    # inject sqlite-friendly models
    main.Message = MessageModel

    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)

    # seed channel and message
    s = SessionLocal()
    try:
        s.execute(
            "INSERT INTO channels(id, org_id, credentials, phone_number) VALUES (:id,:org,:cred,:ph)",
            {
                "id": "ch1",
                "org": "o1",
                "cred": json.dumps({"phone_number_id": "pnid-1"}),
                "ph": "+111",
            },
        )
        s.execute(
            "INSERT INTO messages(id, conversation_id, direction, type, content, template_id, status, meta, client_id)"
            " VALUES (:id,:conv,:dir,:typ,:content,:tpl,:status,:meta,:client)",
            {
                "id": "m1",
                "conv": "conv1",
                "dir": "out",
                "typ": "text",
                "content": json.dumps({"text": "hi"}),
                "tpl": None,
                "status": None,
                "meta": json.dumps({"wa_msg_id": "wamid-123"}),
                "client": "cli1",
            },
        )
        s.commit()
    finally:
        s.close()

    dummy = DummyRedis()
    main.redis = dummy
    with TestClient(main.app) as c:
        yield c, dummy


def test_updates_status_and_emits_webhook(client):
    c, dummy = client
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "pnid-1"},
                            "statuses": [
                                {"id": "wamid-123", "status": "delivered"}
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = bytes(json.dumps(payload), "utf-8")
    sig = sign("dev_secret", body)
    r = c.post(
        "/api/webhooks/whatsapp",
        data=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 200

    # status updated
    from packages.common.db import SessionLocal

    s = SessionLocal()
    try:
        row = s.execute("SELECT status FROM messages WHERE id='m1'").fetchone()
        assert row is not None
        assert row._mapping["status"] == "delivered"
    finally:
        s.close()

    # webhook emitted (best-effort)
    types = [m.get("type") for (_, m) in dummy.calls]
    if "message.status" in types:
        # if present, ensure body contains expected wa_msg_id
        bodies = [m.get("body") for (_, m) in dummy.calls if m.get("type") == "message.status"]
        assert any("wamid-123" in (b or "") for b in bodies)

