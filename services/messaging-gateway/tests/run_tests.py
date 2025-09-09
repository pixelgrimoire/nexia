import sys
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
import sys, types
# provide a tiny fake pythonjsonlogger for local tests
if 'pythonjsonlogger' not in sys.modules:
    fake = types.ModuleType('pythonjsonlogger')
    class _Fmt:
        class JsonFormatter:
            def __init__(self, *a, **k):
                pass
            def format(self, record):
                # minimal formatter used in tests: produce a simple message string
                msg = record.getMessage() if hasattr(record, 'getMessage') else str(record)
                return f"{record.levelname}:{record.name}:{msg}"
    fake.jsonlogger = _Fmt
    sys.modules['pythonjsonlogger'] = fake
# provide a tiny fake redis module
if 'redis' not in sys.modules:
    fake_redis = types.ModuleType('redis')
    class _FakeRedis:
        @staticmethod
        def from_url(*a, **k):
            return _FakeRedis()
    fake_redis.Redis = _FakeRedis
    sys.modules['redis'] = fake_redis
spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
send_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_worker)

failed = []

def ok(cond, msg):
    if not cond:
        failed.append(msg)


def test_process_message_forwards_orig_text():
    class FakeRedis:
        def __init__(self):
            self.xadd_calls = []
        def xadd(self, stream, mapping):
            self.xadd_calls.append((stream, dict(mapping)))
    fake = FakeRedis()
    send_worker.redis = fake
    fields = {"to": "9876", "text": "reply text", "client_id": "cid1", "orig_text": "PIPE_ENTER_TEST"}
    import asyncio
    asyncio.run(send_worker.process_message("1-0", fields))
    ok(len(fake.xadd_calls) == 1, f"expected one xadd call, got {len(fake.xadd_calls)}")
    stream, mapping = fake.xadd_calls[0]
    ok(stream == "nf:sent", f"stream mismatch: {stream}")
    ok(mapping.get("orig_text") == "PIPE_ENTER_TEST", f"orig_text missing: {mapping}")

if __name__ == '__main__':
    test_process_message_forwards_orig_text()
    if failed:
        print("FAILED:\n" + "\n".join(failed))
        sys.exit(1)
    print("ALL TESTS PASSED")
    sys.exit(0)
