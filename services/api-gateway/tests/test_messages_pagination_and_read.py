import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String
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


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client(tmp_path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"
    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    main.Conversation = ConversationModel
    main.Message = MessageModel

    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)

    # seed a conversation and a few messages
    s = SessionLocal()
    try:
        from sqlalchemy import text as sqltext
        s.execute(sqltext('INSERT INTO conversations (id, org_id, contact_id, channel_id, state) VALUES ("cv1","o1","ct1","wa_main","open")'))
        s.execute(sqltext('INSERT INTO messages (id, conversation_id, direction, type, content, status, client_id) VALUES ("m1","cv1","in","text","{""text"": ""hola""}",NULL,"c1")'))
        s.execute(sqltext('INSERT INTO messages (id, conversation_id, direction, type, content, status, client_id) VALUES ("m2","cv1","out","text","{""text"": ""ok""}",NULL,"c2")'))
        s.execute(sqltext('INSERT INTO messages (id, conversation_id, direction, type, content, status, client_id) VALUES ("m3","cv1","in","text","{""text"": ""gracias""}",NULL,"c3")'))
        s.commit()
    finally:
        s.close()

    with TestClient(main.app) as c:
        yield c


def test_pagination_and_mark_read(client: TestClient):
    token = make_token("admin", org_id="o1")

    # list with limit=2 offset=0 -> expect first two ordered by id (m1, m2)
    r = client.get("/api/conversations/cv1/messages", headers={"Authorization": f"Bearer {token}"}, params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert ids == ["m1", "m2"]

    # next page offset=2 -> expect m3
    r = client.get("/api/conversations/cv1/messages", headers={"Authorization": f"Bearer {token}"}, params={"limit": 2, "offset": 2})
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert ids == ["m3"]

    # mark read up to m2 (should set m1 to read; only direction=in)
    r = client.post("/api/conversations/cv1/messages/read", headers={"Authorization": f"Bearer {token}"}, json={"up_to_id": "m2"})
    assert r.status_code == 200
    # Verify statuses via new read -> fetch all and check first inbound
    r = client.get("/api/conversations/cv1/messages", headers={"Authorization": f"Bearer {token}"})
    data = r.json()
    m1 = next(x for x in data if x["id"] == "m1")
    # Note: response model doesn't include status; we indirectly validate via DB in a follow-up SELECT
    from packages.common.db import SessionLocal
    from sqlalchemy import text
    s = SessionLocal()
    try:
        row = s.execute(text("SELECT status FROM messages WHERE id='m1'")).fetchone()
        assert row is not None and row._mapping["status"] == "read"
        row2 = s.execute(text("SELECT status FROM messages WHERE id='m3'")).fetchone()
        assert row2 is not None and row2._mapping["status"] is None
    finally:
        s.close()
