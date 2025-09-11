import importlib.util
import os
from datetime import datetime, timedelta
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base


DBBase = declarative_base()


class ContactModel(DBBase):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    phone = Column(String)
    wa_id = Column(String)
    name = Column(String)
    attributes = Column(JSON)


class ConversationModel(DBBase):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    contact_id = Column(String)
    channel_id = Column(String)
    state = Column(String)


class MessageModel(DBBase):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    conversation_id = Column(String)
    direction = Column(String)
    type = Column(String)
    content = Column(JSON)
    client_id = Column(String)
    created_at = Column(DateTime)


class DummyRedis:
    def xadd(self, *args, **kwargs):
        return None


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


def _load_main():
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    return main


def test_send_text_blocked_outside_24h(tmp_path):
    # Setup env and load app
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"
    main = _load_main()
    # Override ORM models and create tables
    main.Contact = ContactModel  # type: ignore
    main.Conversation = ConversationModel  # type: ignore
    main.Message = MessageModel  # type: ignore
    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)
    # Seed contact, conversation, and an inbound message older than 24h
    s = SessionLocal()
    try:
        s.add(ContactModel(id="c1", org_id="o1", phone="123", wa_id="123", name="Ana", attributes={}))
        s.add(ConversationModel(id="v1", org_id="o1", contact_id="c1", channel_id="wa_main", state="open"))
        old = datetime.utcnow() - timedelta(hours=48)
        s.add(MessageModel(id="m1", conversation_id="v1", direction="in", type="text", content={"text": "hola"}, client_id=None, created_at=old))
        s.commit()
    finally:
        s.close()
    # Inject redis stub
    main.redis = DummyRedis()
    token = make_token("admin", org_id="o1")
    with TestClient(main.app) as client:
        r = client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel_id": "wa_main", "to": "123", "type": "text", "text": "hola"},
        )
        assert r.status_code == 422
        # Verify metric exposed
        m = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})
        assert m.status_code == 200
        body = m.text
        assert "nexia_api_gateway_window_blocked_total" in body
