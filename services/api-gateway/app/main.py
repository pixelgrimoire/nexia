import os, json, time, asyncio, uuid
from uuid import uuid4
from enum import Enum
import jwt
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text, func, or_
from sqlalchemy.orm import Session
from packages.common.db import engine, SessionLocal
from packages.common.models import (
    Organization,
    User,
    Conversation,
    Message,
    Contact,
    Channel,
    RefreshToken,
    Template as DBTemplate,
    Flow as DBFlow,
)
import bcrypt
from collections import defaultdict
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
import http.client
from prometheus_client import CollectorRegistry, Counter, generate_latest, CONTENT_TYPE_LATEST

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

# WhatsApp 24h messaging window enforcement (text outside 24h requires template)
WA_WINDOW_ENFORCE = os.getenv("WA_WINDOW_ENFORCE", "true").lower() == "true"
try:
    WA_WINDOW_HOURS = int(os.getenv("WA_WINDOW_HOURS", "24"))
except Exception:
    WA_WINDOW_HOURS = 24

# Internal URL for Messaging Gateway (used for channel verification)
MGW_INTERNAL_URL = os.getenv("MGW_INTERNAL_URL", "http://messaging-gateway:8000")

# simple in-process fixed-window rate limiter: key -> {window_ts: count}
_rate_counters: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
# simple in-process metrics
RL_LIMITED_COUNT = 0
IDEMP_REUSE_COUNT = 0
PROM_REGISTRY = CollectorRegistry()
RL_LIMITED_METRIC = Counter('nexia_api_gateway_rate_limit_limited_total','Rate limited requests', registry=PROM_REGISTRY)
IDEMP_REUSE_METRIC = Counter('nexia_api_gateway_idempotency_reuse_total','Idempotency reuse count', registry=PROM_REGISTRY)
WINDOW_BLOCKED_METRIC = Counter('nexia_api_gateway_window_blocked_total','Text messages blocked due to 24h window', registry=PROM_REGISTRY)

def _inc_rl_limited():
    global RL_LIMITED_COUNT
    RL_LIMITED_COUNT += 1
    try:
        RL_LIMITED_METRIC.inc()
    except Exception:
        pass


def _inc_idemp_reuse():
    global IDEMP_REUSE_COUNT
    IDEMP_REUSE_COUNT += 1
    try:
        IDEMP_REUSE_METRIC.inc()
    except Exception:
        pass

def reset_rate_limit():
    _rate_counters.clear()

def _enforce_rate_limit(key: str):
    if not RATE_LIMIT_ENABLED:
        return
    # Prefer Redis fixed window per minute; fall back to in-memory
    try:
        now_min = int(time.time() // 60)
        rkey = f"rl:{key}:{now_min}"
        count = redis.incr(rkey)
        if count == 1:
            redis.expire(rkey, 60)
        if count > RATE_LIMIT_PER_MIN:
            _inc_rl_limited()
            raise HTTPException(status_code=429, detail="rate-limit-exceeded")
        return
    except Exception:
        pass
    now_min = int(time.time() // 60)
    bucket = _rate_counters[key]
    for k in list(bucket.keys()):
        if k != now_min:
            bucket.pop(k, None)
    bucket[now_min] += 1
    if bucket[now_min] > RATE_LIMIT_PER_MIN:
        _inc_rl_limited()
        raise HTTPException(status_code=429, detail="rate-limit-exceeded")


def _get_idempotent_cached(key: Optional[str]) -> Optional[dict]:
    if not key:
        return None
    try:
        val = redis.get(key)
        if val:
            try:
                return json.loads(val)
            except Exception:
                return None
    except Exception:
        return None
    return None


def _set_idempotent_cached(key: Optional[str], payload: dict, ttl: int = 600) -> None:
    if not key:
        return
    try:
        redis.set(key, json.dumps(payload), ex=ttl)
    except Exception:
        pass

def _tpl_language_from_payload(tpl: dict) -> Optional[str]:
    try:
        lang = tpl.get("language")
        if isinstance(lang, dict):
            code = lang.get("code") or lang.get("locale") or lang.get("name")
            return str(code) if code else None
        if isinstance(lang, str):
            return lang
    except Exception:
        return None
    return None

def _require_template_approved(db: Session, org_id: str, tpl: dict) -> None:
    name = (tpl or {}).get("name")
    lang = _tpl_language_from_payload(tpl) or "es"
    if not name:
        raise HTTPException(status_code=400, detail="template-invalid")
    try:
        row = (
            db.query(DBTemplate)
            .filter(DBTemplate.org_id == str(org_id))
            .filter(DBTemplate.name == name)
            .filter(DBTemplate.language == lang)
            .first()
        )
    except Exception:
        row = None
    if not row or getattr(row, "status", None) != "approved":
        raise HTTPException(status_code=422, detail="template-not-approved")

def _fetch_mgw_status() -> Optional[dict]:
    try:
        u = urlparse(MGW_INTERNAL_URL)
        host = u.hostname or "messaging-gateway"
        port = u.port or (443 if (u.scheme or "http") == "https" else 80)
        path = "/internal/status"
        conn = http.client.HTTPSConnection(host, port, timeout=3) if (u.scheme or "http") == "https" else http.client.HTTPConnection(host, port, timeout=3)
        conn.request("GET", path, headers={"Host": u.hostname or host})
        resp = conn.getresponse()
        if resp.status >= 200 and resp.status < 300:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except Exception:
                return None
        return None
    except Exception:
        return None

class SendMessage(BaseModel):
    channel_id: str
    to: str
    type: str  # text|template|media
    text: str | None = None
    template: dict | None = None
    media: dict | None = None  # {kind: image|document|video|audio, link: url, caption?: str}
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
    if request.url.path.startswith("/api/healthz") or request.url.path.startswith("/internal/status") or request.url.path.startswith("/metrics") or request.url.path.startswith("/api/auth/dev-login") or request.url.path.startswith("/api/auth/register") or request.url.path.startswith("/api/auth/login") or request.url.path.startswith("/api/auth/refresh"):
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
async def send_message(body: SendMessage, user: dict = require_roles(Role.admin, Role.agent), request: Request = None, db: Session = Depends(lambda: SessionLocal())):
    # rate limit per org+route
    _enforce_rate_limit(f"send:{user.get('org_id','anon')}")
    # idempotency
    idem_key = None
    try:
        hdr = request.headers.get('Idempotency-Key') if request else None
        if hdr:
            idem_key = f"idemp:{user.get('org_id','')}:send:{hdr}"
            cached = _get_idempotent_cached(idem_key)
            if cached:
                _inc_idemp_reuse()
                return cached
    except Exception:
        pass
    # Support both Pydantic v1 (dict) and v2 (model_dump)
    if hasattr(body, "model_dump"):
        payload = body.model_dump()
    else:
        payload = body.dict()
    payload.setdefault("client_id", f"cli_{int(time.time()*1000)}")
    # validate type-specific fields and normalize nested dicts as JSON strings for Redis streams
    msg_type = payload.get("type")
    if msg_type not in ("text", "template", "media"):
        raise HTTPException(status_code=400, detail="invalid-type")
    if msg_type == "text":
        if not payload.get("text"):
            raise HTTPException(status_code=400, detail="text-required")
    elif msg_type == "template":
        tpl = payload.get("template")
        if not isinstance(tpl, dict) or not tpl.get("name"):
            raise HTTPException(status_code=400, detail="template-invalid")
        # Enforce approved template for compliance
        try:
            _require_template_approved(db, user.get("org_id"), tpl)
        except HTTPException:
            raise
        except Exception:
            # if DB unavailable, fail safe in dev by rejecting
            raise HTTPException(status_code=503, detail="template-check-failed")
        payload["template"] = json.dumps(tpl)
    elif msg_type == "media":
        media = payload.get("media")
        if not isinstance(media, dict) or media.get("kind") not in ("image", "document", "video", "audio") or not media.get("link"):
            raise HTTPException(status_code=400, detail="media-invalid")
        payload["media"] = json.dumps(media)
    # Enforce WhatsApp 24h window for text messages when possible (best-effort)
    if WA_WINDOW_ENFORCE and msg_type == "text":
        try:
            org_id = str(user.get("org_id"))
            ch_id = str(payload.get("channel_id"))
            to_val = str(payload.get("to"))
            # Attempt to resolve conversation(s) by contact for this org/channel
            # Strategy: find contact by wa_id/phone; then look up latest IN message for any conversation in that channel
            ct = (
                db.query(Contact)
                .filter(Contact.org_id == org_id)
                .filter((Contact.wa_id == to_val) | (Contact.phone == to_val))
                .first()
            )
            last_in = None
            if ct is not None:
                try:
                    # Join messages via conversations to filter by channel
                    # Without explicit joins, do two steps for SQLite simplicity
                    conv_ids = [r.id for r in db.query(Conversation).filter(Conversation.org_id == org_id).filter(Conversation.contact_id == ct.id).filter(Conversation.channel_id == ch_id).all()]
                    if conv_ids:
                        q = db.query(Message).filter(Message.conversation_id.in_(conv_ids)).filter(Message.direction == "in")
                        # Prefer created_at desc when available
                        order_col = getattr(Message, 'created_at', Message.id)
                        last_in = q.order_by(order_col.desc()).first()
                except Exception:
                    last_in = None
            # Be permissive when no inbound history exists; otherwise require within window
            within_window = True if last_in is None else False
            if last_in is not None:
                ts = getattr(last_in, 'created_at', None)
                if ts is not None:
                    from datetime import datetime, timedelta
                    try:
                        within_window = (datetime.utcnow() - ts) <= timedelta(hours=WA_WINDOW_HOURS)
                    except Exception:
                        within_window = True
            if not within_window:
                raise HTTPException(status_code=422, detail="outside-24h-window - use approved template")
        except HTTPException:
            raise
        except Exception:
            # If any error occurs while checking, default to permissive in dev
            pass
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
    result = {"queued": True, "client_id": payload["client_id"]}
    _set_idempotent_cached(idem_key, result)
    return result


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


# --- Auth real (MVP) --------------------------------------------------------

class RegisterBody(BaseModel):
    email: str
    password: str
    org_name: str
    role: str | None = "admin"


class LoginBody(BaseModel):
    email: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode()


def _verify_password(pw: str, pw_hash: str | None) -> bool:
    if not pw_hash:
        return False
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        return False


def _mint_access(user: User, ttl_sec: int = 15 * 60) -> str:
    now = int(time.time())
    payload = {
        "sub": user.id,
        "org_id": user.org_id,
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + ttl_sec,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


from datetime import datetime, timedelta


def _mint_refresh(user: User, db: Session, days: int = 7) -> str:
    token = str(uuid.uuid4())
    exp_dt = datetime.utcnow() + timedelta(days=days)
    rt = RefreshToken(id=str(uuid.uuid4()), user_id=user.id, token=token, expires_at=exp_dt)
    db.add(rt)
    db.commit()
    return token


@app.post("/api/auth/register", response_model=TokenPair)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.name == body.org_name).first()
    if not org:
        org = Organization(id=str(uuid4()), name=body.org_name)
        db.add(org)
        db.commit()
        db.refresh(org)
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="email-already-registered")
    user = User(id=str(uuid4()), org_id=org.id, email=body.email, role=body.role or Role.admin.value, status="active", password_hash=_hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    access = _mint_access(user)
    refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@app.post("/api/auth/login", response_model=TokenPair)
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid-credentials")
    access = _mint_access(user)
    refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


class RefreshBody(BaseModel):
    refresh_token: str


@app.post("/api/auth/refresh", response_model=TokenPair)
def refresh_token(body: RefreshBody, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token == body.refresh_token).first()
    if not rt or getattr(rt, "revoked", "false") == "true":
        raise HTTPException(status_code=401, detail="invalid-refresh")
    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="invalid-refresh")
    # rotate
    rt.revoked = "true"
    db.commit()
    access = _mint_access(user)
    new_refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": new_refresh, "token_type": "bearer"}


class LogoutBody(BaseModel):
    refresh_token: str | None = None


@app.post("/api/auth/logout")
def logout(body: LogoutBody, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if body.refresh_token:
        rt = db.query(RefreshToken).filter(RefreshToken.token == body.refresh_token).first()
        if rt:
            rt.revoked = "true"
            db.commit()
        return {"ok": True}
    db.query(RefreshToken).filter(RefreshToken.user_id == user.get("sub")).update({RefreshToken.revoked: "true"})
    db.commit()
    return {"ok": True}
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
    unread: int | None = None


class ConversationUpdate(BaseModel):
    state: str | None = None
    assignee: str | None = None


class MessageCreate(BaseModel):
    type: str  # text|template|media
    text: str | None = None
    template: dict | None = None
    media: dict | None = None  # {kind: image|document|video|audio, link: url, caption?: str}
    client_id: str | None = None


@app.post("/api/conversations", response_model=ConversationOut)
def create_conversation(body: ConversationCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    org_id = str(user.get("org_id"))
    # Resolve contact: accept either an existing contact_id or a phone/wa_id; auto-create if missing
    contact = None
    try:
        contact = db.get(Contact, body.contact_id)
    except Exception:
        contact = None
    if not contact:
        # treat provided value as phone/wa_id and look up within org
        q = db.query(Contact).filter(Contact.org_id == org_id).filter((Contact.wa_id == body.contact_id) | (Contact.phone == body.contact_id))
        contact = q.first()
    if not contact:
        # create a minimal contact
        from uuid import uuid4 as _uuid4
        val = body.contact_id
        is_phone = bool(val and (val.isdigit() or val.startswith("+")))
        contact = Contact(id=str(_uuid4()), org_id=org_id, wa_id=val if is_phone else None, phone=val if is_phone else None, name=None, attributes={})
        db.add(contact)
        db.commit()
        db.refresh(contact)
    # Ensure channel belongs to org when channels table is available; otherwise tolerate in MVP
    try:
        ch = db.get(Channel, body.channel_id)
        if ch is not None and str(getattr(ch, "org_id", None)) != org_id:
            raise HTTPException(status_code=404, detail="channel not found")
    except Exception:
        # channels table may not exist under sqlite test setup
        pass
    # Create conversation
    cid = str(uuid4())
    state = body.state or "open"
    conv = Conversation(
        id=cid,
        org_id=org_id,
        contact_id=contact.id,
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
def list_conversations(state: str | None = None, limit: int = 50, include_unread: bool = False, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    q = db.query(Conversation).filter(Conversation.org_id == user.get("org_id"))
    if state:
        q = q.filter(Conversation.state == state)
    rows = q.limit(min(limit, 200)).all()
    out: list[ConversationOut] = []
    for r in rows:
        unread = None
        if include_unread:
            try:
                unread = (
                    db.query(func.count(Message.id))
                    .filter(Message.conversation_id == r.id)
                    .filter(Message.direction == "in")
                    .filter(or_(Message.status != "read", Message.status.is_(None)))
                    .scalar()
                )
                unread = int(unread or 0)
            except Exception:
                unread = 0
        out.append(
            ConversationOut(
                id=r.id,
                org_id=r.org_id,
                contact_id=r.contact_id,
                channel_id=r.channel_id,
                state=r.state,
                assignee=r.assignee,
                unread=unread,
            )
        )
    return out


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
    status: str | None = None
    meta: dict | None = None


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
        out.append(
            MessageOut(
                id=r.id,
                conversation_id=r.conversation_id,
                direction=r.direction,
                type=r.type,
                content=r.content,
                client_id=r.client_id,
                status=getattr(r, "status", None),
                meta=getattr(r, "meta", None),
            )
        )
    return out


@app.post("/api/conversations/{conv_id}/messages", response_model=MessageOut)
def create_message(conv_id: str, body: MessageCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal()), request: Request = None):
    _enforce_rate_limit(f"convmsg:{user.get('org_id','anon')}")
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    # idempotency check before mutating
    idem_key = None
    try:
        hdr = request.headers.get('Idempotency-Key') if request else None
        if hdr:
            idem_key = f"idemp:{user.get('org_id','')}:convmsg:{conv_id}:{hdr}"
            cached = _get_idempotent_cached(idem_key)
            if cached:
                _inc_idemp_reuse()
                # response conforms to MessageOut; use cached directly
                return cached
    except Exception:
        pass
    # validate and normalize by type
    msg_type = body.type
    if msg_type not in ("text", "template", "media"):
        raise HTTPException(status_code=400, detail="invalid-type")

    # Enforce WhatsApp 24h window for text messages (template messages are allowed anytime)
    if WA_WINDOW_ENFORCE and msg_type == "text":
        try:
            # find most recent inbound message for this conversation
            last_in = (
                db.query(Message)
                .filter(Message.conversation_id == conv.id)
                .filter(Message.direction == "in")
                .order_by(getattr(Message, 'created_at', Message.id).desc())
                .first()
            )
        except Exception:
            last_in = None
        # Be permissive when no inbound history exists (MVP/dev)
        within_window = True if last_in is None else False
        if last_in is not None:
            ts = getattr(last_in, 'created_at', None)
            if ts is not None:
                try:
                    from datetime import datetime, timedelta
                    within_window = (datetime.utcnow() - ts) <= timedelta(hours=WA_WINDOW_HOURS)
                except Exception:
                    within_window = True
        if not within_window:
            try:
                WINDOW_BLOCKED_METRIC.inc()
            except Exception:
                pass
            raise HTTPException(status_code=422, detail="outside-24h-window - use approved template")
    content: dict | None = None
    tpl_json: str | None = None
    media_json: str | None = None
    if msg_type == "text":
        if not body.text:
            raise HTTPException(status_code=400, detail="text-required")
        content = {"text": body.text}
    elif msg_type == "template":
        tpl = body.template
        if not isinstance(tpl, dict) or not tpl.get("name"):
            raise HTTPException(status_code=400, detail="template-invalid")
        # Enforce approved template
        try:
            _require_template_approved(db, user.get("org_id"), tpl)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="template-check-failed")
        tpl_json = json.dumps(tpl)
        content = {"template": tpl}
    elif msg_type == "media":
        media = body.media
        if not isinstance(media, dict) or media.get("kind") not in ("image", "document", "video", "audio") or not media.get("link"):
            raise HTTPException(status_code=400, detail="media-invalid")
        media_json = json.dumps(media)
        content = {"media": media}

    mid = str(uuid4())
    m = Message(
        id=mid,
        conversation_id=conv.id,
        direction="out",
        type=msg_type,
        content=content,
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
        payload = {
            "channel_id": conv.channel_id,
            "to": to_value,
            "type": msg_type,
            "client_id": m.client_id,
            "org_id": str(user.get("org_id", "")),
            "requested_by": str(user.get("sub", "")),
            "conversation_id": conv.id,
        }
        if msg_type == "text":
            payload["text"] = body.text or ""
        elif msg_type == "template" and tpl_json is not None:
            payload["template"] = tpl_json
        elif msg_type == "media" and media_json is not None:
            payload["media"] = media_json
        redis.xadd("nf:outbox", payload)
    except Exception:
        pass

    out = MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        direction=m.direction,
        type=m.type,
        content=m.content,
        client_id=m.client_id,
        status=getattr(m, "status", None),
        meta=getattr(m, "meta", None),
    )
    _set_idempotent_cached(idem_key, out.dict() if hasattr(out, 'dict') else out.model_dump())
    return out


@app.get("/internal/status")
async def internal_status():
    return {
        "rate_limit": {
            "enabled": RATE_LIMIT_ENABLED,
            "per_min": RATE_LIMIT_PER_MIN,
            "limited": RL_LIMITED_COUNT,
        },
        "idempotency": {
            "reuse": IDEMP_REUSE_COUNT,
        },
        "service": {
            "ts": time.time(),
            "name": "api-gateway",
        },
    }


@app.get("/metrics")
async def metrics():
    try:
        data = generate_latest(PROM_REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)
    except Exception:
        return Response(content=b"", media_type=CONTENT_TYPE_LATEST)


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
    try:
        ch = db.get(Channel, ch_id)
    except Exception:
        # Missing table or other DB error in minimal/dev environments
        return None
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


class ChannelVerifyOut(BaseModel):
    ok: bool
    status: str | None = None  # ok|warning|error
    fake: bool | None = None
    has_token: bool | None = None
    phone_id: str | None = None
    match: bool | None = None
    details: str | None = None


@app.post("/api/channels/{ch_id}/verify", response_model=ChannelVerifyOut)
def verify_channel(ch_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    pnid = _get_pnid(getattr(ch, "credentials", None))
    st = _fetch_mgw_status()
    if st is None:
        return ChannelVerifyOut(ok=False, status="warning", details="messaging-gateway unreachable")
    try:
        info = (((st or {}).get("workers", {}) or {}).get("send_worker", {}) or {})
        fake = bool(info.get("fake"))
        has_token = bool(info.get("has_token"))
        phone_id = info.get("phone_id")
        match = (pnid is None) or (phone_id == pnid)
        # ok in FAKE mode too, but mark it in status/details
        ok = match and (has_token or fake)
        status = "ok" if ok else "warning"
        details = None if ok else ("phone_id mismatch" if pnid and phone_id and phone_id != pnid else "missing token or phone_id")
        if ok and fake:
            details = "fake-mode"
        return ChannelVerifyOut(ok=ok, status=status, fake=fake, has_token=has_token, phone_id=phone_id, match=match, details=details)
    except Exception:
        return ChannelVerifyOut(ok=False, status="error", details="invalid mgw status format")


# ----------------------------------------------------------------------------
# Templates (MVP)


class TemplateCreate(BaseModel):
    name: str
    language: str = "es"
    category: str | None = None  # marketing|utility|authentication (guidance)
    body: str | None = None
    variables: dict | list | None = None
    status: str | None = "draft"  # draft|approved|rejected|disabled


class TemplateUpdate(BaseModel):
    name: str | None = None
    language: str | None = None
    category: str | None = None
    body: str | None = None
    variables: dict | list | None = None
    status: str | None = None


class TemplateOut(BaseModel):
    id: str
    org_id: str
    name: str | None = None
    language: str | None = None
    category: str | None = None
    body: str | None = None
    variables: dict | list | None = None
    status: str | None = None


def _ensure_unique_template(db: Session, org_id: str, name: str, language: str, exclude_id: str | None = None):
    q = db.query(DBTemplate).filter(DBTemplate.org_id == org_id)
    q = q.filter(DBTemplate.name == name, DBTemplate.language == language)
    if exclude_id:
        q = q.filter(DBTemplate.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail="template name+language already exists")


@app.post("/api/templates", response_model=TemplateOut)
def create_template(body: TemplateCreate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    # basic validation
    if not body.name or not body.language:
        raise HTTPException(status_code=400, detail="name and language required")
    _ensure_unique_template(db, user.get("org_id"), body.name, body.language)
    tid = str(uuid4())
    row = DBTemplate(
        id=tid,
        org_id=user.get("org_id"),
        name=body.name,
        language=body.language,
        category=body.category,
        body=body.body,
        variables=body.variables if isinstance(body.variables, (dict, list)) else None,
        status=body.status or "draft",
    )
    db.add(row)
    db.commit()
    return TemplateOut(
        id=row.id,
        org_id=row.org_id,
        name=row.name,
        language=row.language,
        category=row.category,
        body=row.body,
        variables=row.variables,
        status=row.status,
    )


@app.get("/api/templates", response_model=list[TemplateOut])
def list_templates(user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    rows = db.query(DBTemplate).filter(DBTemplate.org_id == user.get("org_id")).all()
    out: list[TemplateOut] = []
    for r in rows:
        out.append(
            TemplateOut(
                id=r.id,
                org_id=r.org_id,
                name=r.name,
                language=r.language,
                category=r.category,
                body=r.body,
                variables=r.variables,
                status=r.status,
            )
        )
    return out


def _load_template_for_org(db: Session, tpl_id: str, org_id: str) -> DBTemplate | None:
    r = db.get(DBTemplate, tpl_id)
    if not r or r.org_id != org_id:
        return None
    return r


@app.get("/api/templates/{tpl_id}", response_model=TemplateOut)
def get_template(tpl_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    r = _load_template_for_org(db, tpl_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="template not found")
    return TemplateOut(id=r.id, org_id=r.org_id, name=r.name, language=r.language, category=r.category, body=r.body, variables=r.variables, status=r.status)


@app.put("/api/templates/{tpl_id}", response_model=TemplateOut)
def update_template(tpl_id: str, body: TemplateUpdate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_template_for_org(db, tpl_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="template not found")
    # enforce uniqueness when changing name/language
    new_name = body.name if body.name is not None else r.name
    new_lang = body.language if body.language is not None else r.language
    if new_name and new_lang:
        _ensure_unique_template(db, user.get("org_id"), new_name, new_lang, exclude_id=r.id)
    if body.name is not None:
        r.name = body.name
    if body.language is not None:
        r.language = body.language
    if body.category is not None:
        r.category = body.category
    if body.body is not None:
        r.body = body.body
    if body.variables is not None:
        r.variables = body.variables if isinstance(body.variables, (dict, list)) else None
    if body.status is not None:
        r.status = body.status
    db.commit()
    db.refresh(r)
    return TemplateOut(id=r.id, org_id=r.org_id, name=r.name, language=r.language, category=r.category, body=r.body, variables=r.variables, status=r.status)


@app.delete("/api/templates/{tpl_id}")
def delete_template(tpl_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_template_for_org(db, tpl_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="template not found")
    db.delete(r)
    db.commit()
    return {"ok": True}

# ----------------------------------------------------------------------------
# Flows (CRUD + publish semantics)


class FlowCreate(BaseModel):
    name: str
    version: int | None = 1
    graph: dict | None = None
    status: str | None = "draft"  # draft|active|inactive


class FlowUpdate(BaseModel):
    name: str | None = None
    version: int | None = None
    graph: dict | None = None
    status: str | None = None  # when set to active, inactivate others


class FlowOut(BaseModel):
    id: str
    org_id: str
    name: str | None = None
    version: int | None = None
    graph: dict | None = None
    status: str | None = None
    created_by: str | None = None


@app.get("/api/flows", response_model=list[FlowOut])
def list_flows(user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    rows = db.query(DBFlow).filter(DBFlow.org_id == user.get("org_id")).order_by(getattr(DBFlow, 'version', 0).desc()).all()
    out: list[FlowOut] = []
    for r in rows:
        out.append(FlowOut(id=r.id, org_id=r.org_id, name=r.name, version=r.version, graph=r.graph if isinstance(r.graph, dict) else None, status=r.status, created_by=r.created_by))
    return out


@app.post("/api/flows", response_model=FlowOut)
def create_flow(body: FlowCreate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    fid = str(uuid4())
    # if activating this flow, mark others inactive
    if body.status == "active":
        try:
            db.query(DBFlow).filter(DBFlow.org_id == user.get("org_id")).update({DBFlow.status: "inactive"})
            db.commit()
        except Exception:
            db.rollback()
    row = DBFlow(id=fid, org_id=user.get("org_id"), name=body.name, version=body.version or 1, graph=body.graph if isinstance(body.graph, dict) else None, status=body.status or "draft", created_by=str(user.get("sub")))
    db.add(row)
    db.commit()
    return FlowOut(id=row.id, org_id=row.org_id, name=row.name, version=row.version, graph=row.graph if isinstance(row.graph, dict) else None, status=row.status, created_by=row.created_by)


def _load_flow_for_org(db: Session, flow_id: str, org_id: str) -> DBFlow | None:
    r = db.get(DBFlow, flow_id)
    if not r or r.org_id != org_id:
        return None
    return r


@app.get("/api/flows/{flow_id}", response_model=FlowOut)
def get_flow(flow_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    r = _load_flow_for_org(db, flow_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="flow not found")
    return FlowOut(id=r.id, org_id=r.org_id, name=r.name, version=r.version, graph=r.graph if isinstance(r.graph, dict) else None, status=r.status, created_by=r.created_by)


@app.put("/api/flows/{flow_id}", response_model=FlowOut)
def update_flow(flow_id: str, body: FlowUpdate, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_flow_for_org(db, flow_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="flow not found")
    # handle publish semantics
    if body.status == "active":
        try:
            db.query(DBFlow).filter(DBFlow.org_id == user.get("org_id")).filter(DBFlow.id != r.id).update({DBFlow.status: "inactive"})
            db.commit()
        except Exception:
            db.rollback()
    if body.name is not None:
        r.name = body.name
    if body.version is not None:
        r.version = body.version
    if body.graph is not None:
        r.graph = body.graph if isinstance(body.graph, dict) else None
    if body.status is not None:
        r.status = body.status
    db.commit()
    db.refresh(r)
    return FlowOut(id=r.id, org_id=r.org_id, name=r.name, version=r.version, graph=r.graph if isinstance(r.graph, dict) else None, status=r.status, created_by=r.created_by)


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_flow_for_org(db, flow_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="flow not found")
    db.delete(r)
    db.commit()
    return {"ok": True}

# ----------------------------------------------------------------------------
# Contacts (CRUD + simple search) — mirrors services/contacts for convenience

try:
    from pydantic import ConfigDict  # type: ignore
    _MODEL_CONFIG = ConfigDict(from_attributes=True)
except Exception:
    _MODEL_CONFIG = None


class ContactBase(BaseModel):
    org_id: str | None = None
    wa_id: str | None = None
    phone: str | None = None
    name: str | None = None
    attributes: dict | None = None
    tags: list[str] | None = None
    consent: str | None = None
    locale: str | None = None
    timezone: str | None = None


class ContactCreate(ContactBase):
    id: str | None = None


class ContactUpdate(BaseModel):
    wa_id: str | None = None
    phone: str | None = None
    name: str | None = None
    attributes: dict | None = None
    tags: list[str] | None = None
    consent: str | None = None
    locale: str | None = None
    timezone: str | None = None


class ContactOut(ContactBase):
    id: str

    if _MODEL_CONFIG is not None:
        model_config = _MODEL_CONFIG
    else:
        class Config:  # type: ignore
            orm_mode = True


@app.post("/api/contacts", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    cid = payload.id or str(uuid4())
    token_org = str(user.get("org_id"))
    # Enforce org from token; prevent cross-org writes
    if payload.org_id and payload.org_id != token_org:
        raise HTTPException(status_code=403, detail="forbidden: org mismatch")
    org_id = payload.org_id or token_org
    contact = Contact(
        id=cid,
        org_id=org_id,
        wa_id=payload.wa_id,
        phone=payload.phone,
        name=payload.name,
        attributes=payload.attributes or {},
        tags=payload.tags or [],
        consent=payload.consent,
        locale=payload.locale,
        timezone=payload.timezone,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return ContactOut(
        id=contact.id,
        org_id=contact.org_id,
        wa_id=contact.wa_id,
        phone=contact.phone,
        name=contact.name,
        attributes=contact.attributes,
        tags=contact.tags,
        consent=contact.consent,
        locale=contact.locale,
        timezone=contact.timezone,
    )


@app.get("/api/contacts", response_model=list[ContactOut])
def list_contacts(user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    rows = db.query(Contact).filter(Contact.org_id == user.get("org_id")).all()
    out: list[ContactOut] = []
    for c in rows:
        out.append(ContactOut(
            id=c.id,
            org_id=c.org_id,
            wa_id=c.wa_id,
            phone=c.phone,
            name=c.name,
            attributes=getattr(c, 'attributes', None) or {},
            tags=getattr(c, 'tags', None) or [],
            consent=getattr(c, 'consent', None),
            locale=getattr(c, 'locale', None),
            timezone=getattr(c, 'timezone', None),
        ))
    return out


def _load_contact_for_org(db: Session, contact_id: str, org_id: str) -> Contact | None:
    try:
        c = db.get(Contact, contact_id)
    except Exception:
        c = None
    if not c or str(getattr(c, 'org_id', None)) != str(org_id):
        return None
    return c


@app.get("/api/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    c = _load_contact_for_org(db, contact_id, user.get("org_id"))
    if not c:
        raise HTTPException(status_code=404, detail="contact not found")
    return ContactOut(
        id=c.id,
        org_id=c.org_id,
        wa_id=c.wa_id,
        phone=c.phone,
        name=c.name,
        attributes=c.attributes,
        tags=c.tags,
        consent=c.consent,
        locale=c.locale,
        timezone=c.timezone,
    )


@app.put("/api/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: str, payload: ContactUpdate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    c = _load_contact_for_org(db, contact_id, user.get("org_id"))
    if not c:
        raise HTTPException(status_code=404, detail="contact not found")
    # Use model_dump when running Pydantic v2, fall back to dict() for v1.
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(exclude_unset=True)
    else:
        data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return ContactOut(
        id=c.id,
        org_id=c.org_id,
        wa_id=c.wa_id,
        phone=c.phone,
        name=c.name,
        attributes=c.attributes,
        tags=c.tags,
        consent=c.consent,
        locale=c.locale,
        timezone=c.timezone,
    )


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    c = _load_contact_for_org(db, contact_id, user.get("org_id"))
    if not c:
        raise HTTPException(status_code=404, detail="contact not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


@app.get("/api/contacts/search", response_model=list[ContactOut])
def search_contacts(
    tags: List[str] | None = None,
    attr_key: str | None = None,
    attr_value: str | None = None,
    user: dict = require_roles(Role.admin, Role.agent),
    db: Session = Depends(lambda: SessionLocal()),
):
    rows = db.query(Contact).filter(Contact.org_id == user.get("org_id")).all()
    # in-memory filters (MVP)
    if tags:
        rows = [c for c in rows if set(tags).issubset(set((getattr(c, 'tags', None) or [])))]
    if attr_key and attr_value:
        tmp: list[Any] = []
        for c in rows:
            attrs = getattr(c, 'attributes', None) or {}
            try:
                if str(attrs.get(attr_key)) == attr_value:
                    tmp.append(c)
            except Exception:
                pass
        rows = tmp
    out: list[ContactOut] = []
    for c in rows:
        out.append(ContactOut(
            id=c.id,
            org_id=c.org_id,
            wa_id=c.wa_id,
            phone=c.phone,
            name=c.name,
            attributes=getattr(c, 'attributes', None) or {},
            tags=getattr(c, 'tags', None) or [],
            consent=getattr(c, 'consent', None),
            locale=getattr(c, 'locale', None),
            timezone=getattr(c, 'timezone', None),
        ))
    return out
