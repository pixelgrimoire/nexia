import os, json, time, asyncio
from fastapi import FastAPI, Header, Request
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from packages.common.db import engine

app = FastAPI(title="NexIA API Gateway")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

class SendMessage(BaseModel):
	channel_id: str
	to: str
	type: str  # text|template
	text: str | None = None
	template: dict | None = None
	client_id: str | None = None

@app.on_event("startup")
def init_db():
	# Create tables if models exist -- keep minimal to avoid forcing migrations here
	try:
		with engine.begin() as conn:
			conn.execute(text("""
			-- Tables are created elsewhere; this is a no-op placeholder to ensure engine is importable
			"""))
	except Exception:
		# ignore DB errors in dev when Postgres isn't available yet
		pass

@app.get("/api/healthz")
async def healthz():
	return {"ok": True, "ts": time.time()}

@app.post("/api/messages/send")
async def send_message(body: SendMessage, authorization: str | None = Header(None)):
	payload = body.dict()
	payload.setdefault("client_id", f"cli_{int(time.time()*1000)}")
	# Publish to outbox stream for messaging-gateway
	try:
		redis.xadd("nf:outbox", payload)
	except Exception:
		# in case redis is unavailable, return a useful response
		return {"queued": False, "reason": "redis-unavailable"}
	return {"queued": True, "client_id": payload["client_id"]}

# SSE inbox stream using sse-starlette-style EventSourceResponse
from sse_starlette.sse import EventSourceResponse

@app.get("/api/inbox/stream")
async def inbox_stream(request: Request):
	async def event_gen():
		last_id = "$"
		while True:
			if await request.is_disconnected():
				break
			try:
				items = redis.xread({"nf:inbox": last_id}, block=1000, count=1)
				if not items:
					await asyncio.sleep(0.1)
					continue
				# xread returns list of (stream, [(id, {k:v}), ...])
				for stream, msgs in items:
					for msg_id, fields in msgs:
						last_id = msg_id
						data = fields.get("payload") or json.dumps(fields)
						yield {"event": "message", "id": msg_id, "data": data}
			except Exception:
				await asyncio.sleep(1)
	return EventSourceResponse(event_gen())
