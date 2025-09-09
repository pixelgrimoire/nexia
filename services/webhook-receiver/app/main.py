import os, hmac, hashlib, json, logging
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
        logger.info("raw webhook body: %s", body.decode(errors="replace"))
        payload = await req.json()
        # Fan-out: inbox (SSE) y flujo entrante
        try:
                redis.xadd("nf:inbox", {"source": "wa", "payload": json.dumps(payload)})
                redis.xadd("nf:incoming", {"source": "wa", "payload": json.dumps(payload)})
	except Exception:
		# if redis unavailable, still return ok to webhook sender to avoid retries
		return {"ok": True, "warning": "redis-unavailable"}
	return {"ok": True}
