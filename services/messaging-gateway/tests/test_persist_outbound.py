import importlib.util
import importlib
import os
from pathlib import Path
import asyncio
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base


DBBase = declarative_base()


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


class FakeRedis:
    def __init__(self):
        self.xadd_calls = []
    def xadd(self, stream, mapping):
        self.xadd_calls.append((stream, dict(mapping)))


def test_persist_outbound_with_conversation(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    # reload DB
    import packages.common.db as common_db
    importlib.reload(common_db)

    # prepare DB tables and seed
    from packages.common.db import engine, SessionLocal
    DBBase.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        s.add(ContactModel(id="ct1", org_id="o1", phone="123", wa_id="123", name="Ana", attributes={}))
        s.add(ConversationModel(id="cv1", org_id="o1", contact_id="ct1", channel_id="wa_main", state="open", assignee=None))
        s.commit()
    finally:
        s.close()

    # Load worker and patch DB models via import path
    root = Path(__file__).resolve().parents[3]
    module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
    spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
    send_worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(send_worker)

    # Replace redis
    fake = FakeRedis()
    send_worker.redis = fake
    send_worker.FAKE = True
    # Override ORM models to match our sqlite schema
    send_worker.DBMessage = MessageModel
    send_worker.DBConversation = ConversationModel
    send_worker.DBContact = ContactModel

    # Process message with conversation_id present
    fields = {"to": "123", "text": "hi", "client_id": "cid1", "org_id": "o1", "channel_id": "wa_main", "conversation_id": "cv1"}
    asyncio.run(send_worker.process_message("1-0", fields))

    # Verify persisted message exists
    from sqlalchemy import text
    s = SessionLocal()
    try:
        row = s.execute(text("SELECT conversation_id, direction, type, content FROM messages")).fetchone()
        assert row is not None
        assert row._mapping["conversation_id"] == "cv1"
        assert row._mapping["direction"] == "out"
    finally:
        s.close()
