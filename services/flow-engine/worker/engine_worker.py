import os, json, time, asyncio, logging, uuid
from pythonjsonlogger import jsonlogger
from redis import Redis

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger("engine_worker")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

def parse_kvs(kvs):
	"""Normalize redis XREAD key/value payloads into a dict of strings.

	Accepts either a dict or a flat list (k, v, k, v, ...), with bytes or str values.
	Returns a dict[str, str] or None on failure.
	"""
	try:
		fields = {}
		if isinstance(kvs, dict):
			for k, v in kvs.items():
				fields[str(k)] = str(v)
		else:
			for i in range(0, len(kvs), 2):
				k = kvs[i].decode() if isinstance(kvs[i], bytes) else kvs[i]
				v = kvs[i+1].decode() if isinstance(kvs[i+1], bytes) else kvs[i+1]
				fields[str(k)] = str(v)
		return fields
	except Exception:
		logger.exception("parse_kvs failed")
		return None

def classify_intent(text: str) -> str:
	t = (text or "").lower()
	if "precio" in t or "costo" in t or "precio" in t:
		return "pricing"
	if "hola" in t or "buenas" in t:
		return "greeting"
	return "default"

async def handle_message(msg_id: str, fields: dict):
	payload_raw = fields.get("payload") or fields.get("body") or ""
	try:
		payload = json.loads(payload_raw)
	except Exception:
		payload = {"text": payload_raw}
	# try to extract text from common WA structure
	text = ""
	# Common webhook path: entry->[0]->changes->[0]->value->messages->[0]->text->body
	try:
		entry = payload.get("entry", [])
		if entry:
			changes = entry[0].get("changes", [])
			if changes:
				value = changes[0].get("value", {})
				messages = value.get("messages", [])
				if messages:
					text = messages[0].get("text", {}).get("body", "")
	except Exception:
		pass
	if not text:
		# fallback to a top-level text
		text = payload.get("text") or payload.get("message") or ""

	intent = classify_intent(text)
	# simple action: reply with a template based on intent
	if intent == "pricing":
		reply = f"Gracias por preguntar sobre precios. Nuestro plan starter cuesta $9/mes."
	elif intent == "greeting":
		reply = "Hola! ¿En qué puedo ayudarte hoy?"
	else:
		reply = "Gracias por tu mensaje. Un agente te responderá pronto."

	# publish to outbox (so messaging-gateway will pick it)
	# publish reply and keep original text in metadata for tracing
	try:
		trace_id = str(uuid.uuid4())
		out = {"channel_id": "wa_main", "to": payload.get("contact", {}).get("phone", "unknown"), "type": "text", "text": reply, "client_id": f"auto_{int(time.time()*1000)}", "orig_text": text, "trace_id": trace_id}
		# ensure all values are strings for redis stream
		redis.xadd("nf:outbox", {k: str(v) for k, v in out.items()})
		# log the published message with trace_id for observability
		logger.info("published nf:outbox message", extra={"trace_id": trace_id, "to": out.get("to"), "client_id": out.get("client_id")})
	except Exception:
		logger.exception("engine xadd failed")

async def loop():
	# start from the beginning in dev so backlog is processed
	last_id = "0-0"
	logger.info("engine_worker starting")
	while True:
		try:
			# Use Redis XREAD via execute_command for consistent server semantics across clients
			raw = await asyncio.to_thread(redis.execute_command, 'XREAD', 'BLOCK', 5000, 'COUNT', 1, 'STREAMS', 'nf:incoming', last_id)
			if not raw:
				# no messages during block
				await asyncio.sleep(0.1)
				continue
			# raw format: [[b'stream', [[b'id', [b'k', b'v', ...]], ...]], ...]
			for stream_item in raw:
				msgs = stream_item[1]
				for msg in msgs:
					msg_id = msg[0].decode() if isinstance(msg[0], bytes) else msg[0]
					kvs = msg[1]
					# convert flat list or dict into dict of strings
					fields = {}
					try:
						if isinstance(kvs, dict):
							for k, v in kvs.items():
								fields[str(k)] = str(v)
						else:
							for i in range(0, len(kvs), 2):
								k = kvs[i].decode() if isinstance(kvs[i], bytes) else kvs[i]
								v = kvs[i+1].decode() if isinstance(kvs[i+1], bytes) else kvs[i+1]
								fields[k] = v
					except Exception:
						logger.exception("engine_worker failed parsing XREAD fields")
						continue
					last_id = msg_id
					await handle_message(msg_id, fields)
		except Exception:
			logger.exception("engine error")
			await asyncio.sleep(1)

if __name__ == "__main__":
	asyncio.run(loop())
