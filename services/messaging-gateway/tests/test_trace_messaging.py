import asyncio
import importlib.util
from pathlib import Path

# Load send_worker by file path
root = Path(__file__).resolve().parents[2].parent
module_path = root / "services" / "messaging-gateway" / "worker" / "send_worker.py"
spec = importlib.util.spec_from_file_location("send_worker", str(module_path))
send_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_worker)


def test_process_message_preserves_trace_id(monkeypatch):
    captured = {}

    def fake_xadd(stream, mapping):
        captured['stream'] = stream
        captured['mapping'] = mapping

    monkeypatch.setattr(send_worker, 'redis', type('R', (), {'xadd': fake_xadd}))

    fields = {'to': '9876', 'text': 'reply', 'client_id': 'cid1', 'orig_text': 'PIPE_ENTER_TEST', 'trace_id': 'tid-1234'}

    asyncio.run(send_worker.process_message('1-0', fields))

    assert captured.get('stream') == 'nf:sent'
    mapping = captured.get('mapping')
    assert mapping is not None
    assert mapping.get('trace_id') == 'tid-1234'
    assert mapping.get('orig_text') == 'PIPE_ENTER_TEST'
