import asyncio
import json
import importlib.util
from pathlib import Path

# Load engine_worker by file path to avoid package import issues
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "flow-engine" / "worker" / "engine_worker.py"
spec = importlib.util.spec_from_file_location("engine_worker", str(module_path))
engine_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine_worker)


def test_handle_message_adds_trace_id(monkeypatch):
    captured = {}

    def fake_xadd(stream, mapping):
        captured['stream'] = stream
        captured['mapping'] = mapping

    monkeypatch.setattr(engine_worker, 'redis', type('R', (), {'xadd': fake_xadd}))

    # Build a minimal fields dict containing a payload with contact phone
    payload = {'contact': {'phone': '12345'}, 'text': 'hola'}
    fields = {'payload': json.dumps(payload)}

    # call the coroutine
    asyncio.run(engine_worker.handle_message('1-0', fields))

    assert captured.get('stream') == 'nf:outbox'
    mapping = captured.get('mapping')
    assert mapping is not None
    # mapping values are strings
    assert 'trace_id' in mapping and mapping['trace_id']
    assert mapping.get('orig_text') == 'hola'
