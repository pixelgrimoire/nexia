import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest


def load_engine_worker():
    root = Path(__file__).resolve().parents[2].parent
    module_path = root / "services" / "flow-engine" / "worker" / "engine_worker.py"
    spec = importlib.util.spec_from_file_location("engine_worker", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


class FakeRedis:
    def __init__(self):
        self.zadds = []
        self.xadds = []

    def zadd(self, key, mapping):
        self.zadds.append((key, dict(mapping)))

    def xadd(self, stream, mapping):
        self.xadds.append((stream, dict(mapping)))


@pytest.fixture
def engine(tmp_path):
    # set up sqlite DB
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    mod = load_engine_worker()
    # create flows table
    from packages.common.db import engine as db_engine
    from packages.common.models import Base

    # create only flows and contacts
    tables = [
        Base.metadata.tables["flows"],
        Base.metadata.tables["contacts"],
    ]
    Base.metadata.create_all(bind=db_engine, tables=tables)
    return mod


def test_wait_schedules_resume(engine):
    from packages.common.db import SessionLocal
    from packages.common.models import Flow

    # seed an active flow with wait in path_default
    graph = {
        "nodes": [{"id": "n1", "type": "intent", "map": {"default": "p"}}],
        "paths": {
            "p": [
                {"type": "action", "action": "send_text", "text": "hola"},
                {"type": "wait", "seconds": 1},
                {"type": "action", "action": "send_text", "text": "luego"},
            ]
        },
    }
    s = SessionLocal()
    try:
        s.add(Flow(id="f1", org_id="o1", name="f", version=1, graph=graph, status="active", created_by="t"))
        s.commit()
    finally:
        s.close()

    # replace redis with fake
    fake = FakeRedis()
    engine.redis = fake

    payload = {"text": "hola"}
    fields = {"payload": json.dumps(payload), "org_id": "o1", "channel_id": "wa_main"}

    asyncio.run(engine.handle_message("1-0", fields))

    # should have scheduled exactly one resume
    assert len(fake.zadds) == 1
    zkey, zmap = fake.zadds[0]
    assert zkey == os.getenv("FLOW_ENGINE_SCHED_ZSET", "nf:incoming:scheduled")
    # mapping key is serialized JSON of the item
    item_raw = next(iter(zmap.keys()))
    item = json.loads(item_raw)
    resume = json.loads(item.get("engine_resume"))
    assert resume["path"] == "p"
    assert resume["index"] == 2


def test_set_attribute_updates_contact(engine):
    from packages.common.db import SessionLocal
    from packages.common.models import Flow, Contact

    # seed contact and flow with set_attribute
    s = SessionLocal()
    try:
        s.add(Contact(id="c1", org_id="o1", wa_id="123", phone="123", name="Ana", attributes={}))
        graph = {
            "nodes": [{"id": "n1", "type": "intent", "map": {"default": "p"}}],
            "paths": {
                "p": [
                    {"type": "set_attribute", "key": "vip", "value": True},
                    {"type": "action", "action": "send_text", "text": "ok"},
                ]
            },
        }
        s.add(Flow(id="f1", org_id="o1", name="f", version=1, graph=graph, status="active", created_by="t"))
        s.commit()
    finally:
        s.close()

    fake = FakeRedis()
    engine.redis = fake

    payload = {"contact": {"phone": "123"}, "text": "hola"}
    fields = {"payload": json.dumps(payload), "org_id": "o1", "channel_id": "wa_main"}

    asyncio.run(engine.handle_message("1-1", fields))

    # verify attribute updated
    s = SessionLocal()
    try:
        ct = s.get(Contact, "c1")
        assert ct is not None
        assert (ct.attributes or {}).get("vip") is True
    finally:
        s.close()

