import sys
import importlib.util
from pathlib import Path
import types
import sys

# If redis isn't installed in the local dev environment, provide a tiny fake
# module so importing engine_worker succeeds for unit tests that don't use redis.
if 'redis' not in sys.modules:
    fake_redis = types.ModuleType('redis')
    class _FakeRedis:
        @staticmethod
        def from_url(*a, **k):
            return _FakeRedis()
    fake_redis.Redis = _FakeRedis
    sys.modules['redis'] = fake_redis

# Load engine_worker module by file path to avoid package name issues
# compute repo root from tests location
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "flow-engine" / "worker" / "engine_worker.py"
spec = importlib.util.spec_from_file_location("engine_worker", str(module_path))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
parse_kvs = engine.parse_kvs

failed = []

def ok(cond, msg):
    if not cond:
        failed.append(msg)


def test_parse_kvs_with_dict():
    kvs = {"body": '{"text": "hello"}', "client_id": "abc"}
    out = parse_kvs(kvs)
    ok(out is not None, "dict -> out is None")
    ok(out.get("body") == '{"text": "hello"}', f"body mismatch: {out}")
    ok(out.get("client_id") == "abc", f"client_id mismatch: {out}")


def test_parse_kvs_with_flat_list_bytes():
    kvs = [b'body', b'{"text": "hi"}', b'client_id', b'123']
    out = parse_kvs(kvs)
    ok(out is not None, "flat list -> out is None")
    ok(out.get("body") == '{"text": "hi"}', f"body mismatch: {out}")
    ok(out.get("client_id") == '123', f"client_id mismatch: {out}")


def test_parse_kvs_failure_returns_none():
    kvs = [b'body', b'data', b'invalid']
    out = parse_kvs(kvs)
    ok(out is None, f"expected None on invalid input, got: {out}")


if __name__ == '__main__':
    test_parse_kvs_with_dict()
    test_parse_kvs_with_flat_list_bytes()
    test_parse_kvs_failure_returns_none()

    if failed:
        print("FAILED:\n" + "\n".join(failed))
        sys.exit(1)
    print("ALL TESTS PASSED")
    sys.exit(0)
