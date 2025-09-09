import asyncio
import importlib.util
from pathlib import Path

import pytest

# Load send_worker by file path
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
send_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_worker)


def test_process_message_logs_trace_id(monkeypatch, caplog):
    def fake_xadd(stream, mapping):
        return None

    monkeypatch.setattr(send_worker, 'redis', type('R', (), {'xadd': fake_xadd}))

    fields = {'to': '9', 'text': 'x', 'client_id': 'c', 'trace_id': 'tid-xyz'}

    caplog.clear()
    caplog.set_level('INFO')
    asyncio.run(send_worker.process_message('1-0', fields))

    found = any(getattr(r, 'trace_id', None) == 'tid-xyz' for r in caplog.records)
    assert found, f"expected trace_id tid-xyz in logs, got: {[r.getMessage() for r in caplog.records]}"
