import os, json, time, asyncio
from uuid import uuid4
from enum import Enum
import jwt
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session
from packages.common.db import engine, SessionLocal
from packages.common.models import Organization, User, Conversation, Message, Contact, Channel
from collections import defaultdict

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
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
DEV_LOGIN_ENABLED = os.getenv("DEV_LOGIN_ENABLED", "true").lower() == "true"
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
try:
    RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
except Exception:
    RATE_LIMIT_PER_MIN = 60

# simple in-process fixed-window rate limiter: key -> {window_ts: count}
_rate_counters: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

def reset_rate_limit():
    _rate_counters.clear()

def _enforce_rate_limit(key: str):
    if not RATE_LIMIT_ENABLED:
        return
    now_min = int(time.time() // 60)
    bucket = _rate_counters[key]
    # drop old windows to avoid growth
    for k in list(bucket.keys()):
        if k != now_min:
            bucket.pop(k, None)
    bucket[now_min] += 1
    if bucket[now_min] > RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate-limit-exceeded")

class SendMessage(BaseModel):
    channel_id: str
    to: str
    type: str  # text|template
    text: str | None = None
    template: dict | None = None
    client_id: str | None = None

# Startup logic is handled by the lifespan handler defined above


class Role(str, Enum):
    admin = "admin"
    agent = "agent"


def require_roles(*roles: Role):
    async def checker(request: Request):
        user = getattr(request.state, "user", None)
        if not user or user.get("role") not in [r.value for r in roles]:
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return Depends(checker)


@app.middleware("http")
async def jwt_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/healthz") or request.url.path.startswith("/api/auth/dev-login"):
        return await call_next(request)
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return JSONResponse({"detail": "invalid-token"}, status_code=401)
    request.state.user = payload
    return await call_next(request)

@app.get("/api/healthz")
async def healthz():
	return {"ok": True, "ts": time.time()}


@app.post("/api/messages/send")
async def send_message(body: SendMessage, user: dict = require_roles(Role.admin, Role.agent)):
    # rate limit per org+route
    _enforce_rate_limit(f"send:{user.get('org_id','anon')}")
    # Support both Pydantic v1 (dict) and v2 (model_dump)
    if hasattr(body, "model_dump"):
        payload = body.model_dump()
    else:
        payload = body.dict()
    payload.setdefault("client_id", f"cli_{int(time.time()*1000)}")
    # tenancy enrichment
    if user:
        payload.setdefault("org_id", str(user.get("org_id", "")))
        payload.setdefault("requested_by", str(user.get("sub", "")))
    # Publish to outbox stream for messaging-gateway
    try:
        redis.xadd("nf:outbox", payload)
    except Exception:
        # in case redis is unavailable, return a useful response
        return {"queued": False, "reason": "redis-unavailable"}
    return {"queued": True, "client_id": payload["client_id"]}


# SSE inbox stream using sse-starlette-style EventSourceResponse
@app.get("/api/inbox/stream")
async def inbox_stream(request: Request, user: dict = require_roles(Role.admin, Role.agent)):
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


# --- Auth/dev endpoints -----------------------------------------------------
class DevLoginBody(BaseModel):
    email: str
    org_name: str
    role: str | None = None  # defaults to admin if missing


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _mint_jwt(claims: dict) -> str:
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


@app.post("/api/auth/dev-login", response_model=TokenOut)
def dev_login(body: DevLoginBody, db: Session = Depends(get_db)):
    if not DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=404, detail="not-found")
    # find or create organization by name
    org = db.query(Organization).filter(Organization.name == body.org_name).first()
    if not org:
        org = Organization(id=str(uuid4()), name=body.org_name)
        db.add(org)
        db.commit()
        db.refresh(org)
    # find or create user by email
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        user = User(id=str(uuid4()), org_id=org.id, email=body.email, role=body.role or Role.admin.value)
        db.add(user)
        db.commit()
        db.refresh(user)
    # align role if provided
    if body.role and user.role != body.role:
        user.role = body.role
        db.commit()
        db.refresh(user)
    now = int(time.time())
    exp = now + 7 * 24 * 3600
    token = _mint_jwt({"sub": user.id, "org_id": org.id, "email": user.email, "role": user.role, "iat": now, "exp": exp})
    return {"access_token": token, "token_type": "bearer"}


from fastapi import Request


def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user
# ----------------------------------------------------------------------------
# Conversations & Messages (Inbox MVP)


class ConversationCreate(BaseModel):
    contact_id: str
    channel_id: str
    assignee: str | None = None
    state: str | None = None  # open|pending|closed (default open)


class ConversationOut(BaseModel):
    id: str
    contact_id: str
    channel_id: str
    org_id: str
    state: str | None = None
    assignee: str | None = None


class ConversationUpdate(BaseModel):
    state: str | None = None
    assignee: str | None = None


class MessageCreate(BaseModel):
    type: str  # text|template (MVP: text)
    text: str | None = None
    client_id: str | None = None


@app.post("/api/conversations", response_model=ConversationOut)
def create_conversation(body: ConversationCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    cid = str(uuid4())
    state = body.state or "open"
    conv = Conversation(
        id=cid,
        org_id=user.get("org_id"),
        contact_id=body.contact_id,
        channel_id=body.channel_id,
        state=state,
        assignee=body.assignee,
    )
    db.add(conv)
    db.commit()
    return ConversationOut(
        id=conv.id,
        org_id=conv.org_id,
        contact_id=conv.contact_id,
        channel_id=conv.channel_id,
        state=conv.state,
        assignee=conv.assignee,
    )


@app.get("/api/conversations", response_model=list[ConversationOut])
def list_conversations(state: str | None = None, limit: int = 50, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    q = db.query(Conversation).filter(Conversation.org_id == user.get("org_id"))
    if state:
        q = q.filter(Conversation.state == state)
    rows = q.limit(min(limit, 200)).all()
    return [ConversationOut(id=r.id, org_id=r.org_id, contact_id=r.contact_id, channel_id=r.channel_id, state=r.state, assignee=r.assignee) for r in rows]


def _load_conv_for_org(db: Session, conv_id: str, org_id: str) -> Conversation | None:
    conv = db.get(Conversation, conv_id)
    if not conv or conv.org_id != org_id:
        return None
    return conv


@app.get("/api/conversations/{conv_id}", response_model=ConversationOut)
def get_conversation(conv_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ConversationOut(id=conv.id, org_id=conv.org_id, contact_id=conv.contact_id, channel_id=conv.channel_id, state=conv.state, assignee=conv.assignee)


@app.put("/api/conversations/{conv_id}", response_model=ConversationOut)
def update_conversation(conv_id: str, body: ConversationUpdate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if body.state is not None:
        conv.state = body.state
    if body.assignee is not None:
        conv.assignee = body.assignee
    db.commit()
    db.refresh(conv)
    return ConversationOut(id=conv.id, org_id=conv.org_id, contact_id=conv.contact_id, channel_id=conv.channel_id, state=conv.state, assignee=conv.assignee)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    direction: str
    type: str
    content: dict | None = None
    client_id: str | None = None


@app.get("/api/conversations/{conv_id}/messages", response_model=list[MessageOut])
def list_messages(conv_id: str, limit: int = 100, offset: int = 0, after_id: str | None = None, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    # order by created_at if available, otherwise id
    order_cols = []
    if hasattr(Message, 'created_at'):
        order_cols.append(getattr(Message, 'created_at'))
    order_cols.append(Message.id)
    q = db.query(Message).filter(Message.conversation_id == conv_id).order_by(*order_cols)
    # cursor by after_id
    if after_id:
        if hasattr(Message, 'created_at'):
            try:
                anchor = db.query(Message).filter(Message.id == after_id).first()
                if anchor and getattr(anchor, 'created_at', None) is not None:
                    q = q.filter(getattr(Message, 'created_at') > getattr(anchor, 'created_at'))
                else:
                    q = q.filter(Message.id > after_id)
            except Exception:
                q = q.filter(Message.id > after_id)
        else:
            q = q.filter(Message.id > after_id)
    if offset:
        q = q.offset(max(offset, 0))
    rows = q.limit(min(limit, 500)).all()
    out: list[MessageOut] = []
    for r in rows:
        out.append(MessageOut(id=r.id, conversation_id=r.conversation_id, direction=r.direction, type=r.type, content=r.content, client_id=r.client_id))
    return out


@app.post("/api/conversations/{conv_id}/messages", response_model=MessageOut)
def create_message(conv_id: str, body: MessageCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    _enforce_rate_limit(f"convmsg:{user.get('org_id','anon')}")
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    mid = str(uuid4())
    m = Message(
        id=mid,
        conversation_id=conv.id,
        direction="out",
        type=body.type,
        content={"text": body.text} if body.text else None,
        client_id=body.client_id or f"cli_{int(time.time()*1000)}",
    )
    db.add(m)
    db.commit()

    # Publish to outbox for messaging-gateway
    to_value = "unknown"
    try:
        c = db.get(Contact, conv.contact_id)
        to_value = (getattr(c, "phone", None) or getattr(c, "wa_id", None) or "unknown") if c else to_value
    except Exception:
        pass
    try:
        redis.xadd(
            "nf:outbox",
            {
                "channel_id": conv.channel_id,
                "to": to_value,
                "type": body.type,
                "text": body.text or "",
                "client_id": m.client_id,
                "org_id": str(user.get("org_id", "")),
                "requested_by": str(user.get("sub", "")),
                "conversation_id": conv.id,
            },
        )
    except Exception:
        pass

    return MessageOut(id=m.id, conversation_id=m.conversation_id, direction=m.direction, type=m.type, content=m.content, client_id=m.client_id)


class MarkReadBody(BaseModel):
    up_to_id: str | None = None


@app.post("/api/conversations/{conv_id}/messages/read")
def mark_messages_read(conv_id: str, body: MarkReadBody, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    q = db.query(Message).filter(Message.conversation_id == conv_id, Message.direction == "in")
    # Without timestamps, apply a basic id-based cutoff when provided
    if body.up_to_id:
        try:
            q = q.filter(Message.id <= body.up_to_id)  # lexical compare in SQLite/Postgres UUID/text
        except Exception:
            pass
    updated = 0
    for msg in q.all():
        if getattr(msg, "status", None) != "read":
            msg.status = "read"
            updated += 1
    if updated:
        db.commit()
    return {"updated": updated}
# ----------------------------------------------------------------------------
# Channels (tenancy + uniqueness)


class ChannelCreate(BaseModel):
    type: str = "whatsapp"
    mode: str = "cloud"
    status: str | None = None
    phone_number: str | None = None
    credentials: dict | None = None  # should contain phone_number_id for WA Cloud


class ChannelUpdate(BaseModel):
    type: str | None = None
    mode: str | None = None
    status: str | None = None
    phone_number: str | None = None
    credentials: dict | None = None


class ChannelOut(BaseModel):
    id: str
    org_id: str
    type: str | None = None
    mode: str | None = None
    status: str | None = None
    phone_number: str | None = None
    credentials: dict | None = None


def _get_pnid(creds: dict | None) -> str | None:
    if not creds:
        return None
    return creds.get("phone_number_id")


def _ensure_unique_channel(db: Session, org_id: str, phone_number: str | None, phone_number_id: str | None, exclude_id: str | None = None):
    rows = db.query(Channel).filter(Channel.org_id == org_id).all()
    for r in rows:
        if exclude_id and r.id == exclude_id:
            continue
        if phone_number and getattr(r, "phone_number", None) == phone_number:
            raise HTTPException(status_code=409, detail="phone_number-already-in-use")
        creds = getattr(r, "credentials", None) or {}
        if phone_number_id and isinstance(creds, dict) and creds.get("phone_number_id") == phone_number_id:
            raise HTTPException(status_code=409, detail="phone_number_id-already-in-use")


@app.post("/api/channels", response_model=ChannelOut)
def create_channel(body: ChannelCreate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ch_id = str(uuid4())
    pnid = _get_pnid(body.credentials)
    if not (body.phone_number or pnid):
        raise HTTPException(status_code=400, detail="missing phone identifier")
    _ensure_unique_channel(db, user.get("org_id"), body.phone_number, pnid)
    ch = Channel(
        id=ch_id,
        org_id=user.get("org_id"),
        type=body.type,
        mode=body.mode,
        status=body.status or "active",
        phone_number=body.phone_number,
        credentials=body.credentials or {},
    )
    db.add(ch)
    db.commit()
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=ch.credentials)


@app.get("/api/channels", response_model=list[ChannelOut])
def list_channels(user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    rows = db.query(Channel).filter(Channel.org_id == user.get("org_id")).all()
    return [ChannelOut(id=r.id, org_id=r.org_id, type=r.type, mode=r.mode, status=r.status, phone_number=r.phone_number, credentials=r.credentials) for r in rows]


def _load_channel_for_org(db: Session, ch_id: str, org_id: str) -> Channel | None:
    ch = db.get(Channel, ch_id)
    if not ch or ch.org_id != org_id:
        return None
    return ch


@app.get("/api/channels/{ch_id}", response_model=ChannelOut)
def get_channel(ch_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=ch.credentials)


@app.put("/api/channels/{ch_id}", response_model=ChannelOut)
def update_channel(ch_id: str, body: ChannelUpdate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    pnid = _get_pnid(body.credentials)
    phone_number = body.phone_number if body.phone_number is not None else ch.phone_number
    pnid_final = pnid if pnid is not None else _get_pnid(ch.credentials)
    _ensure_unique_channel(db, user.get("org_id"), phone_number, pnid_final, exclude_id=ch.id)
    if body.type is not None:
        ch.type = body.type
    if body.mode is not None:
        ch.mode = body.mode
    if body.status is not None:
        ch.status = body.status
    if body.phone_number is not None:
        ch.phone_number = body.phone_number
    if body.credentials is not None:
        ch.credentials = body.credentials
    db.commit()
    db.refresh(ch)
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=ch.credentials)


@app.delete("/api/channels/{ch_id}")
def delete_channel(ch_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    db.delete(ch)
    db.commit()
    return {"ok": True}
