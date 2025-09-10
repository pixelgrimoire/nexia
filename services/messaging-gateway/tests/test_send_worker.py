import importlib.util
from pathlib import Path
import asyncio
import httpx
import json

# Load module by path to avoid package name issues
root = Path(__file__).resolve().parents[3]
module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
send_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_worker)

class FakeRedis:
    def __init__(self):
        self.xadd_calls = []
    def xadd(self, stream, mapping):
        self.xadd_calls.append((stream, dict(mapping)))


def test_process_message_forwards_orig_text():
    fake = FakeRedis()
    # inject fake redis into module
    send_worker.redis = fake

    fields = {"to": "9876", "text": "reply text", "client_id": "cid1", "orig_text": "PIPE_ENTER_TEST"}
    # run the async coroutine
    asyncio.run(send_worker.process_message("1-0", fields))

    assert len(fake.xadd_calls) == 1, "expected one xadd call"
    stream, mapping = fake.xadd_calls[0]
    assert stream == "nf:sent"
    assert mapping.get("orig_text") == "PIPE_ENTER_TEST"
    assert mapping.get("client_id") == "cid1"


def test_process_message_fake_mode(monkeypatch):
    fake = FakeRedis()
    send_worker.redis = fake
    send_worker.FAKE = True

    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return httpx.Response(200, json={})

    monkeypatch.setattr(send_worker.httpx, "post", fake_post)

    fields = {"to": "123", "text": "hi", "client_id": "cid1"}
    asyncio.run(send_worker.process_message("1-0", fields))

    assert called["count"] == 0, "httpx.post should not be called in fake mode"
    stream, mapping = fake.xadd_calls[0]
    assert mapping.get("fake") == "True"


def test_process_message_real_mode(monkeypatch):
    fake = FakeRedis()
    send_worker.redis = fake
    send_worker.FAKE = False
    send_worker.TOKEN = "token"
    send_worker.PHONE_ID = "111"

    called = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        called["url"] = url
        called["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"messages": [{"id": "msg1"}]}, request=request)

    monkeypatch.setattr(send_worker.httpx, "post", fake_post)

    fields = {"to": "123", "text": "hi", "client_id": "cid1"}
    asyncio.run(send_worker.process_message("1-1", fields))

    assert called["url"].endswith("/111/messages"), "expected WhatsApp API URL"
    stream, mapping = fake.xadd_calls[0]
    assert mapping.get("fake") == "False"
    assert mapping.get("wa_msg_id") == "msg1"


def test_process_message_template_real_mode(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
    spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)

    fake = FakeRedis()
    sw.redis = fake
    sw.FAKE = False
    sw.TOKEN = "token"
    sw.PHONE_ID = "111"

    called = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        called["url"] = url
        called["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"messages": [{"id": "msg2"}]}, request=request)

    monkeypatch.setattr(sw.httpx, "post", fake_post)

    tpl = {"name": "welcome", "language": {"code": "es"}}
    fields = {"to": "123", "type": "template", "template": json.dumps(tpl), "client_id": "cid1"}
    asyncio.run(sw.process_message("1-2", fields))

    assert called["url"].endswith("/111/messages")
    body = called["json"]
    assert body["type"] == "template"
    assert body["template"]["name"] == "welcome"


def test_process_message_media_real_mode(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
    spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)

    fake = FakeRedis()
    sw.redis = fake
    sw.FAKE = False
    sw.TOKEN = "token"
    sw.PHONE_ID = "111"

    called = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        called["url"] = url
        called["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"messages": [{"id": "msg3"}]}, request=request)

    monkeypatch.setattr(sw.httpx, "post", fake_post)

    media = {"kind": "image", "link": "https://example.com/img.jpg", "caption": "Hola"}
    fields = {"to": "123", "type": "media", "media": json.dumps(media), "client_id": "cid2"}
    asyncio.run(sw.process_message("1-3", fields))

    assert called["url"].endswith("/111/messages")
    body = called["json"]
    assert body["type"] == "image"
    assert body["image"]["link"].startswith("https://example.com/")
