import os
import hmac
import hashlib
import json
import logging
from json import JSONDecodeError
from fastapi import FastAPI, HTTPException, Request
from redis import Redis
from sqlalchemy import text
from packages.common.db import SessionLocal

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

	# Try enrich with org_id/channel_id via phone_number_id mapping
	org_id = None
	channel_id = None
	try:
		pnid = None
		display = None
		try:
			entry = payload.get("entry", [])
			if entry:
				changes = entry[0].get("changes", [])
				if changes:
					value = changes[0].get("value", {})
					meta = value.get("metadata", {})
					pnid = meta.get("phone_number_id")
					display = meta.get("display_phone_number")
		except Exception:
			pass
		if pnid or display:
			with SessionLocal() as db:
				rows = db.execute(text("SELECT id, org_id, credentials, phone_number FROM channels"))
				for r in rows:
					row = dict(r._mapping)
					creds = row.get("credentials") if isinstance(row.get("credentials"), dict) else None
					if pnid and creds and creds.get("phone_number_id") == pnid:
						channel_id = row.get("id")
						org_id = row.get("org_id")
						break
					if display and row.get("phone_number") == display:
						channel_id = row.get("id")
						org_id = row.get("org_id")
						break
	except Exception:
		logger.exception("channel lookup failed")

	# Fan-out: inbox (SSE) and incoming flow with enrichment when available
	out_common = {"source": "wa", "payload": json.dumps(payload)}
	if org_id:
		out_common["org_id"] = str(org_id)
	if channel_id:
		out_common["channel_id"] = str(channel_id)
	try:
		redis.xadd("nf:inbox", out_common)
		redis.xadd("nf:incoming", out_common)
	except Exception:
		logger.exception("redis unavailable when enqueuing parsed payload")
		return {"ok": True, "warning": "redis-unavailable"}

	return {"ok": True}
