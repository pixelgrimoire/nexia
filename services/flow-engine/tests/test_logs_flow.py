import asyncio
import json
import importlib.util
from pathlib import Path

import pytest

# Load engine_worker by file path
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "flow-engine" / "worker" / "engine_worker.py"
spec = importlib.util.spec_from_file_location("engine_worker", str(module_path))
engine_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine_worker)


def test_handle_message_logs_trace_id(monkeypatch, caplog):
    def fake_xadd(stream, mapping):
        return None

    monkeypatch.setattr(engine_worker, 'redis', type('R', (), {'xadd': fake_xadd}))

    payload = {'contact': {'phone': '111'}, 'text': 'hola'}
    fields = {'payload': json.dumps(payload)}

    caplog.clear()
    caplog.set_level('INFO')
    asyncio.run(engine_worker.handle_message('1-0', fields))

    found = any(getattr(r, 'trace_id', None) for r in caplog.records)
    assert found
