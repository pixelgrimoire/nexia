import importlib
import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base


DBBase = declarative_base()


class ConversationModel(DBBase):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    contact_id = Column(String)
    channel_id = Column(String)
    state = Column(String)
    assignee = Column(String)
    last_activity_at = Column(DateTime)


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


class ContactModel(DBBase):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    phone = Column(String)
    wa_id = Column(String)
    name = Column(String)
    attributes = Column(JSON)


class DummyRedis:
    def __init__(self):
        self.calls = []

    def xadd(self, stream, mapping):
        self.calls.append((stream, dict(mapping)))
        return None


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"

    # Reload DB module for new DATABASE_URL
    import packages.common.db as common_db
    importlib.reload(common_db)

    # Load API module
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # Inject sqlite-friendly models
    main.Conversation = ConversationModel
    main.Message = MessageModel
    main.Contact = ContactModel

    # Create tables
    from packages.common.db import engine, SessionLocal

    DBBase.metadata.create_all(bind=engine)

    # Prepare a contact for routing to 'to'
    s = SessionLocal()
    try:
        s.add(ContactModel(id="c1", org_id="o1", phone="12345", name="Ana", attributes={}))
        s.commit()
    finally:
        s.close()

    dummy = DummyRedis()
    main.redis = dummy
    with TestClient(main.app) as c:
        yield c, dummy


def test_conversation_create_and_send_text(client):
    c, redis = client
    token = make_token("admin", org_id="o1", sub="u9")

    # Create conversation
    r = c.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_id": "c1", "channel_id": "wa_main"},
    )
    assert r.status_code == 200
    conv = r.json()

    # Send message
    r2 = c.post(
        f"/api/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "text", "text": "hola"},
    )
    assert r2.status_code == 200
    assert len(redis.calls) == 1
    stream, mapping = redis.calls[0]
    assert stream == "nf:outbox"
    assert mapping.get("org_id") == "o1"
    assert mapping.get("requested_by") == "u9"
    assert mapping.get("channel_id") == "wa_main"
    assert mapping.get("to") == "12345"

