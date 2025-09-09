import importlib.util
from pathlib import Path
import asyncio

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
