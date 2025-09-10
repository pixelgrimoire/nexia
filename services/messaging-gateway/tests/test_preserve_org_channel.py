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


def test_preserves_org_and_channel_in_sent():
    fake = FakeRedis()
    send_worker.redis = fake
    send_worker.FAKE = True

    fields = {"to": "9876", "text": "hi", "client_id": "c1", "org_id": "o1", "channel_id": "ch1"}
    asyncio.run(send_worker.process_message("1-0", fields))

    assert len(fake.xadd_calls) == 1
    _, mapping = fake.xadd_calls[0]
    assert mapping.get("org_id") == "o1"
    assert mapping.get("channel_id") == "ch1"
