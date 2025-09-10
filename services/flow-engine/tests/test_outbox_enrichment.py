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


def test_outbox_enriched_with_org_and_channel(monkeypatch):
    captured = {}

    def fake_xadd(stream, mapping):
        captured['stream'] = stream
        captured['mapping'] = mapping

    monkeypatch.setattr(engine_worker, 'redis', type('R', (), {'xadd': fake_xadd}))

    # Build WA-like payload with phone_number_id and sender phone
    payload = {
        "entry": [
            {
                "changes": [
                    {"value": {"messages": [{"from": "521111222333", "text": {"body": "hola"}}]}}
                ]
            }
        ]
    }
    fields = {
        'payload': json.dumps(payload),
        'org_id': 'o1',
        'channel_id': 'ch1',
    }

    asyncio.run(engine_worker.handle_message('1-0', fields))

    assert captured.get('stream') == 'nf:outbox'
    mapping = captured.get('mapping')
    assert mapping is not None
    assert mapping.get('org_id') == 'o1'
    assert mapping.get('channel_id') == 'ch1'
    assert mapping.get('to') == '521111222333'
