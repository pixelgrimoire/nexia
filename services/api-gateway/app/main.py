import os, json, time, asyncio
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from packages.common.db import engine

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
	# Create tables if models exist -- minimal no-op to ensure engine is importable
	try:
		with engine.begin() as conn:
			conn.execute(text("""
			-- Tables are created elsewhere; this is a no-op placeholder to ensure engine is importable
			"""))
	except Exception:
		# ignore DB errors in dev when Postgres isn't available yet
		pass
	yield


app = FastAPI(title="NexIA API Gateway", lifespan=lifespan)
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


class SendMessage(BaseModel):
	channel_id: str
	to: str
	type: str  # text|template
	text: str | None = None
	template: dict | None = None
	client_id: str | None = None

# Startup logic is handled by the lifespan handler defined above

@app.get("/api/healthz")
async def healthz():
	return {"ok": True, "ts": time.time()}


@app.post("/api/messages/send")
async def send_message(body: SendMessage, authorization: str | None = Header(None)):
	# Support both Pydantic v1 (dict) and v2 (model_dump)
	if hasattr(body, "model_dump"):
		payload = body.model_dump()
	else:
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
	# Import lazily to avoid import-time failure if sse_starlette isn't installed
	try:
		from sse_starlette.sse import EventSourceResponse
	except Exception:
		return JSONResponse({"error": "sse_starlette not installed"}, status_code=501)
	return EventSourceResponse(event_gen())
