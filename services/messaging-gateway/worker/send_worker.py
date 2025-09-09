import os, asyncio, json, time, logging
from pythonjsonlogger import jsonlogger
from redis import Redis

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
FAKE = os.getenv("WHATSAPP_FAKE_MODE", "true").lower() == "true"
TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger("send_worker")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

async def process_message(msg_id: str, fields: dict):
	to = fields.get("to")
	text = fields.get("text") or (fields.get("body") or "")
	client_id = fields.get("client_id")
	if FAKE:
		result = {"fake": True, "to": to, "text": text, "client_id": client_id, "ts": time.time()}
	else:
		# real send would be implemented here (httpx.post to WhatsApp API)
		result = {"fake": False, "to": to, "text": text, "client_id": client_id, "ts": time.time()}
	try:
		# ensure all values are strings for redis stream
		redis.xadd("nf:sent", {k: str(v) for k, v in result.items()})
	except Exception:
		logger.exception("send_worker xadd error")
	logger.info("processed %s %s", msg_id, result)

async def loop():
	# start from the beginning in dev so backlog is processed
	last_id = "0-0"
	logger.info("send_worker starting (FAKE=%s)", FAKE)
	while True:
		try:
			# Use Redis XREAD via execute_command for consistent blocking reads
			raw = await asyncio.to_thread(redis.execute_command, 'XREAD', 'BLOCK', 5000, 'COUNT', 1, 'STREAMS', 'nf:outbox', last_id)
			if not raw:
				await asyncio.sleep(0.1)
				continue
			for stream_item in raw:
				msgs = stream_item[1]
				for msg in msgs:
					msg_id = msg[0].decode() if isinstance(msg[0], bytes) else msg[0]
					kvs = msg[1]
					# redis client may return fields as a dict or a flat list of pairs
					fields = {}
					if isinstance(kvs, dict):
						# values already decoded when decode_responses=True
						for k, v in kvs.items():
							fields[str(k)] = str(v)
					else:
						for i in range(0, len(kvs), 2):
							k = kvs[i].decode() if isinstance(kvs[i], bytes) else kvs[i]
							v = kvs[i+1].decode() if isinstance(kvs[i+1], bytes) else kvs[i+1]
							fields[k] = v
					last_id = msg_id
					await process_message(msg_id, fields)
		except Exception:
			logger.exception("send_worker loop error")
			await asyncio.sleep(1)

if __name__ == "__main__":
	asyncio.run(loop())
