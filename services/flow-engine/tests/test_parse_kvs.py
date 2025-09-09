import importlib.util
from pathlib import Path

# Load engine_worker by file path to avoid package name issues (flow-engine contains a hyphen)
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "flow-engine" / "worker" / "engine_worker.py"
spec = importlib.util.spec_from_file_location("engine_worker", str(module_path))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
parse_kvs = engine.parse_kvs


def test_parse_kvs_with_dict():
    kvs = {"body": '{"text": "hello"}', "client_id": "abc"}
    out = parse_kvs(kvs)
    assert out["body"] == '{"text": "hello"}'
    assert out["client_id"] == "abc"


def test_parse_kvs_with_flat_list_bytes():
    kvs = [b'body', b'{"text": "hi"}', b'client_id', b'123']
    out = parse_kvs(kvs)
    assert out["body"] == '{"text": "hi"}'
    assert out["client_id"] == '123'


def test_parse_kvs_failure_returns_none():
    # make kvs length odd to trigger exception
    kvs = [b'body', b'data', b'invalid']
    out = parse_kvs(kvs)
    assert out is None
