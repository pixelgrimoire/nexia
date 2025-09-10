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


class ContactModel(DBBase):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    wa_id = Column(String)
    phone = Column(String)
    name = Column(String)
    attributes = Column(JSON)


class ConversationModel(DBBase):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    contact_id = Column(String)
    channel_id = Column(String)
    state = Column(String)
    assignee = Column(String)


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
    def xadd(self, *args, **kwargs):
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

    # inject sqlite-friendly models for persistence
    main.Contact = ContactModel
    main.Conversation = ConversationModel
    main.Message = MessageModel

    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        s.add(ChannelModel(id="ch1", org_id="o1", credentials={"phone_number_id": "pnid-zzz"}, phone_number="+111"))
        s.commit()
    finally:
        s.close()

    main.redis = DummyRedis()
    with TestClient(main.app) as c:
        yield c


def test_persists_inbound_contact_conv_msg(client):
    import json
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "pnid-zzz", "display_phone_number": "+111"},
                            "messages": [
                                {"from": "521777888999", "text": {"body": "hola"}},
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = bytes(json.dumps(payload), "utf-8")
    sig = sign("dev_secret", body)
    r = client.post("/api/webhooks/whatsapp", data=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200

    # Inspect DB for contact, conversation, message
    from packages.common.db import SessionLocal
    s = SessionLocal()
    try:
        # count rows
        contact = s.execute("SELECT id, org_id, wa_id, phone FROM contacts").fetchone()
        assert contact is not None
        assert contact._mapping["org_id"] == "o1"
        assert contact._mapping["wa_id"] == "521777888999"

        conv = s.execute("SELECT id, org_id, contact_id, channel_id, state FROM conversations").fetchone()
        assert conv is not None
        assert conv._mapping["org_id"] == "o1"
        assert conv._mapping["channel_id"] == "ch1"
        assert conv._mapping["state"] == "open"

        msg = s.execute("SELECT id, conversation_id, direction, type, content FROM messages").fetchone()
        assert msg is not None
        assert msg._mapping["direction"] == "in"
        assert msg._mapping["type"] == "text"
    finally:
        s.close()

