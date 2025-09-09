import os
import hmac
import hashlib
import json
import logging
from json import JSONDecodeError
from fastapi import FastAPI, HTTPException, Request
from redis import Redis

app = FastAPI(title="NexIA Webhook Receiver")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "change-me")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "dev_secret").encode()
logger = logging.getLogger(__name__)


@app.get("/api/webhooks/whatsapp")
async def verify(mode: str, challenge: str, verify_token: str):
	if mode == "subscribe" and verify_token == VERIFY_TOKEN:
		# Return numeric challenge as int per WhatsApp verification
		try:
			return int(challenge)
		except Exception:
			return challenge
	raise HTTPException(403, "Forbidden")


@app.post("/api/webhooks/whatsapp")
async def receive(req: Request):
	sig = req.headers.get("X-Hub-Signature-256", "")
	body = await req.body()
	expected = "sha256=" + hmac.new(APP_SECRET, body, hashlib.sha256).hexdigest()
	if not hmac.compare_digest(sig, expected):
		raise HTTPException(403, "Invalid signature")

	raw_text = body.decode(errors="replace")
	logger.info("raw webhook body: %s", raw_text)

	# Try parse JSON, but tolerate malformed payloads to avoid webhook retries
	try:
		payload = json.loads(raw_text)
	except JSONDecodeError:
		logger.error("Invalid JSON webhook body (signature OK). Storing raw payload for inspection.")
		try:
			# store raw payload so it can be inspected manually
			redis.xadd("nf:incoming", {"source": "wa", "payload": raw_text})
		except Exception:
			logger.exception("redis unavailable when enqueuing invalid-json payload")
			return {"ok": True, "warning": "redis-unavailable-invalid-json"}
		return {"ok": True, "warning": "invalid-json"}

	# Fan-out: inbox (SSE) and incoming flow
	try:
		redis.xadd("nf:inbox", {"source": "wa", "payload": json.dumps(payload)})
		redis.xadd("nf:incoming", {"source": "wa", "payload": json.dumps(payload)})
	except Exception:
		logger.exception("redis unavailable when enqueuing parsed payload")
		return {"ok": True, "warning": "redis-unavailable"}

	return {"ok": True}
