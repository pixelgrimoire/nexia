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
    Note,
    Attachment,
    AuditLog,
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

# MinIO/S3 config (optional)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio12345")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "nexia-uploads")

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


def _sanitize_credentials(creds: dict | None) -> dict | None:
    try:
        if not isinstance(creds, dict):
            return None
        c = dict(creds)
        # Never expose access_token in API responses
        if 'access_token' in c:
            c.pop('access_token', None)
        return c
    except Exception:
        return None


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

def _fetch_mgw_metrics() -> dict:
    """Fetch Messaging Gateway internal metrics (JSON) with safe fallbacks."""
    out = {"streams": {"nf_outbox": None, "nf_sent": None}}
    try:
        u = urlparse(MGW_INTERNAL_URL)
        host = u.hostname or "messaging-gateway"
        port = u.port or (443 if (u.scheme or "http") == "https" else 80)
        path = "/internal/metrics"
        conn = http.client.HTTPSConnection(host, port, timeout=3) if (u.scheme or "http") == "https" else http.client.HTTPConnection(host, port, timeout=3)
        conn.request("GET", path, headers={"Host": u.hostname or host})
        resp = conn.getresponse()
        if 200 <= resp.status < 300:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    out = data
            except Exception:
                pass
    except Exception:
        pass
    # fill fallbacks from Redis if missing
    try:
        if out.get("streams", {}).get("nf_outbox") is None:
            out.setdefault("streams", {})["nf_outbox"] = redis.xlen("nf:outbox")
    except Exception:
        pass
    try:
        if out.get("streams", {}).get("nf_sent") is None:
            out.setdefault("streams", {})["nf_sent"] = redis.xlen("nf:sent")
    except Exception:
        pass
    return out


def _minio_client():
    try:
        from minio import Minio  # type: ignore
    except Exception:
        return None
    host = MINIO_ENDPOINT
    secure = MINIO_SECURE
    if host.startswith("http://"):
        host = host[len("http://"):]
        secure = False
    if host.startswith("https://"):
        host = host[len("https://"):]
        secure = True
    try:
        client = Minio(host, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=secure)
        try:
            if not client.bucket_exists(MINIO_BUCKET):
                client.make_bucket(MINIO_BUCKET)
        except Exception:
            pass
        return client
    except Exception:
        return None

def _verify_wa_cloud_phone_id(pnid: Optional[str], access_token: Optional[str]) -> tuple[bool, str | None, Optional[str]]:
    """Best-effort verification against Graph API for WA Cloud credentials.

    Returns (ok, status, phone_id_returned)
    """
    try:
        if not pnid or not access_token:
            return (False, "missing-credentials", None)
        host = "graph.facebook.com"
        path = f"/v20.0/{pnid}?fields=id"
        conn = http.client.HTTPSConnection(host, 443, timeout=4)
        conn.request("GET", path, headers={"Authorization": f"Bearer {access_token}"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        if 200 <= resp.status < 300:
            try:
                data = json.loads(body)
                got = str(data.get("id")) if isinstance(data, dict) else None
                if got == str(pnid):
                    return (True, "ok", got)
                return (False, "mismatch", got)
            except Exception:
                return (False, "invalid-json", None)
        # 401/403 usually means invalid token or scope
        return (False, f"http-{resp.status}", None)
    except Exception:
        return (False, "network-error", None)

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
    owner = "owner"
    admin = "admin"
    agent = "agent"
    analyst = "analyst"


def require_roles(*roles: Role):
    async def checker(request: Request):
        user = getattr(request.state, "user", None)
        user_role = user.get("role") if user else None
        allowed = {r.value for r in roles}
        # Owners inherit admin capabilities by default
        if user_role == Role.owner.value and Role.admin.value in allowed:
            return user
        if not user or user_role not in allowed:
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
async def send_message(body: SendMessage, user: dict = require_roles(Role.admin, Role.agent, Role.owner), request: Request = None, db: Session = Depends(lambda: SessionLocal())):
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
async def inbox_stream(request: Request, user: dict = require_roles(Role.owner, Role.admin, Role.agent)):
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
    default_workspace_id: str | None = None
    workspaces: list[WorkspaceMembershipOut] | None = None


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
    default_ws = None
    try:
        default_ws = _ensure_default_workspace_for_user(db, user)
    except Exception:
        default_ws = None
    memberships_raw = _workspace_memberships_payload(db, user.id)
    memberships = [WorkspaceMembershipOut(**item) for item in memberships_raw]
    default_workspace_id = default_ws.id if default_ws else (memberships_raw[0]["workspace_id"] if memberships_raw else None)
    now = int(time.time())
    exp = now + 7 * 24 * 3600
    token = _mint_jwt({"sub": user.id, "org_id": org.id, "email": user.email, "role": user.role, "iat": now, "exp": exp})
    return {"access_token": token, "token_type": "bearer", "default_workspace_id": default_workspace_id, "workspaces": memberships}


from fastapi import Request


def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


DEFAULT_WORKSPACE_NAME = "Default workspace"
_WORKSPACE_MEMBER_ROLES = {"owner", "admin", "member", "agent", "analyst"}


def _workspace_role_for_user_role(user_role: str | None) -> str:
    role = (user_role or "").lower()
    if role in (Role.owner.value, Role.admin.value):
        return "owner"
    return "member"


def _ensure_workspace_member(db: Session, workspace_id: str, user_id: str, member_role: str) -> WorkspaceMember:
    row = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .filter(WorkspaceMember.user_id == user_id)
        .first()
    )
    target_role = member_role if member_role in _WORKSPACE_MEMBER_ROLES else "member"
    if row:
        if row.role != target_role:
            row.role = target_role
            db.commit()
            db.refresh(row)
        return row
    row = WorkspaceMember(
        id=str(uuid4()),
        workspace_id=workspace_id,
        user_id=user_id,
        role=target_role,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_default_workspace_for_user(db: Session, user: User) -> Workspace:
    org_id = str(user.org_id)
    workspace = (
        db.query(Workspace)
        .filter(Workspace.org_id == org_id)
        .order_by(getattr(Workspace, "created_at", Workspace.id))
        .first()
    )
    if not workspace:
        workspace = Workspace(
            id=str(uuid4()),
            org_id=org_id,
            name=DEFAULT_WORKSPACE_NAME,
            created_at=datetime.utcnow(),
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    _ensure_workspace_member(db, workspace.id, user.id, _workspace_role_for_user_role(user.role))
    return workspace


def _load_workspace_for_org(db: Session, workspace_id: str, org_id: str) -> Workspace | None:
    ws = db.get(Workspace, workspace_id)
    if not ws or str(ws.org_id) != str(org_id):
        return None
    return ws


def _workspace_out(ws: Workspace, member_count: int | None = None) -> dict:
    created_ts = None
    if getattr(ws, "created_at", None):
        try:
            created_ts = ws.created_at.timestamp()
        except Exception:
            created_ts = None
    return {
        "id": ws.id,
        "org_id": ws.org_id,
        "name": ws.name,
        "created_at": created_ts,
        "member_count": int(member_count or 0),
    }


def _workspace_member_out(member: WorkspaceMember, user_row: User | None = None) -> dict:
    created_ts = None
    if getattr(member, "created_at", None):
        try:
            created_ts = member.created_at.timestamp()
        except Exception:
            created_ts = None
    return {
        "id": member.id,
        "workspace_id": member.workspace_id,
        "user_id": member.user_id,
        "role": member.role,
        "created_at": created_ts,
        "user_email": getattr(user_row, "email", None),
        "user_role": getattr(user_row, "role", None),
    }


def _workspace_memberships_payload(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user_id)
        .order_by(getattr(Workspace, "created_at", Workspace.id))
        .all()
    )
    items: list[dict] = []
    for member, ws in rows:
        items.append({"workspace_id": ws.id, "workspace_name": ws.name, "role": member.role})
    return items



class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceUpdate(BaseModel):
    name: str | None = None


class WorkspaceOut(BaseModel):
    id: str
    org_id: str
    name: str
    created_at: float | None = None
    member_count: int = 0


class WorkspaceMemberCreate(BaseModel):
    user_id: str
    role: str = "member"


class WorkspaceMemberUpdate(BaseModel):
    role: str


class WorkspaceMemberOut(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: str
    user_email: str | None = None
    user_role: str | None = None
    created_at: float | None = None


class WorkspaceMembershipOut(BaseModel):
    workspace_id: str
    workspace_name: str
    role: str


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
    default_workspace_id: str | None = None
    workspaces: list[WorkspaceMembershipOut] | None = None


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
    default_ws = None
    try:
        default_ws = _ensure_default_workspace_for_user(db, user)
    except Exception:
        default_ws = None
    memberships_raw = _workspace_memberships_payload(db, user.id)
    memberships = [WorkspaceMembershipOut(**item) for item in memberships_raw]
    default_workspace_id = default_ws.id if default_ws else (memberships_raw[0]["workspace_id"] if memberships_raw else None)
    access = _mint_access(user)
    refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "default_workspace_id": default_workspace_id, "workspaces": memberships}


@app.post("/api/auth/login", response_model=TokenPair)
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid-credentials")
    default_ws = None
    try:
        default_ws = _ensure_default_workspace_for_user(db, user)
    except Exception:
        default_ws = None
    memberships_raw = _workspace_memberships_payload(db, user.id)
    memberships = [WorkspaceMembershipOut(**item) for item in memberships_raw]
    default_workspace_id = default_ws.id if default_ws else (memberships_raw[0]["workspace_id"] if memberships_raw else None)
    access = _mint_access(user)
    refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "default_workspace_id": default_workspace_id, "workspaces": memberships}


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
    default_ws = None
    try:
        default_ws = _ensure_default_workspace_for_user(db, user)
    except Exception:
        default_ws = None
    memberships_raw = _workspace_memberships_payload(db, user.id)
    memberships = [WorkspaceMembershipOut(**item) for item in memberships_raw]
    default_workspace_id = default_ws.id if default_ws else (memberships_raw[0]["workspace_id"] if memberships_raw else None)
    access = _mint_access(user)
    new_refresh = _mint_refresh(user, db)
    return {"access_token": access, "refresh_token": new_refresh, "token_type": "bearer", "default_workspace_id": default_workspace_id, "workspaces": memberships}


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
def list_conversations(state: str | None = None, limit: int = 50, include_unread: bool = False, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
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
def get_conversation(conv_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ConversationOut(id=conv.id, org_id=conv.org_id, contact_id=conv.contact_id, channel_id=conv.channel_id, state=conv.state, assignee=conv.assignee)


@app.put("/api/conversations/{conv_id}", response_model=ConversationOut)
def update_conversation(conv_id: str, body: ConversationUpdate, user: dict = require_roles(Role.admin, Role.agent, Role.owner), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if body.state is not None:
        conv.state = body.state
    if body.assignee is not None:
        conv.assignee = body.assignee
    db.commit()
    db.refresh(conv)
    try:
        _audit(db, user, "conversation.updated", "conversation", conv.id, {"state": conv.state, "assignee": conv.assignee})
    except Exception:
        pass
    # Emit webhook event (best-effort)
    try:
        _publish_webhook_event(
            org_id=str(user.get("org_id")),
            event_type="conversation.updated",
            payload={
                "conversation_id": conv.id,
                "channel_id": conv.channel_id,
                "state": conv.state,
                "assignee": conv.assignee,
            },
        )
    except Exception:
        pass
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


class NoteOut(BaseModel):
    id: str
    conversation_id: str
    author: str | None = None
    body: str
    created_at: float | None = None


class AttachmentOut(BaseModel):
    id: str
    conversation_id: str
    url: str
    filename: str | None = None
    uploaded_by: str | None = None
    created_at: float | None = None


@app.get("/api/conversations/{conv_id}/messages", response_model=list[MessageOut])
def list_messages(conv_id: str, limit: int = 100, offset: int = 0, after_id: str | None = None, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
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


# ----------------------------------------------------------------------------
# Audit helper

def _audit(db: Session, user: dict, action: str, entity_type: str, entity_id: str | None, data: dict | None = None):
    try:
        # ensure table exists (best-effort in dev)
        AuditLog.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    try:
        from datetime import datetime
        row = AuditLog(
            id=str(uuid4()),
            org_id=str(user.get("org_id")),
            actor=str(user.get("email") or user.get("sub") or "user"),
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            data=data if isinstance(data, dict) else None,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass



@app.post("/api/conversations/{conv_id}/messages", response_model=MessageOut)
def create_message(conv_id: str, body: MessageCreate, user: dict = require_roles(Role.admin, Role.agent, Role.owner), db: Session = Depends(lambda: SessionLocal()), request: Request = None):
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
    try:
        _audit(db, user, "message.sent", "message", m.id, {"conversation_id": conv.id, "type": m.type, "client_id": m.client_id})
    except Exception:
        pass
    # Emit webhook event (best-effort)
    try:
        _publish_webhook_event(
            org_id=str(user.get("org_id")),
            event_type="message.sent",
            payload={
                "conversation_id": conv.id,
                "message_id": m.id,
                "type": m.type,
                "direction": m.direction,
                "content": m.content,
                "client_id": m.client_id,
                "channel_id": conv.channel_id,
            },
        )
    except Exception:
        pass
    _set_idempotent_cached(idem_key, out.dict() if hasattr(out, 'dict') else out.model_dump())
    return out


# ----------------------------------------------------------------------------
# Conversation Notes (internal)

class NoteCreate(BaseModel):
    body: str


@app.get("/api/conversations/{conv_id}/notes", response_model=list[NoteOut])
def list_notes(conv_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    # Ensure table exists (best-effort in dev)
    try:
        Note.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    try:
        rows = db.query(Note).filter(Note.conversation_id == conv_id).order_by(getattr(Note, 'created_at', Note.id).desc()).all()
    except Exception:
        rows = []
    out: list[NoteOut] = []
    for n in rows:
        ts = None
        try:
            import datetime
            ts = n.created_at.timestamp() if getattr(n, 'created_at', None) else None
        except Exception:
            ts = None
        out.append(NoteOut(id=n.id, conversation_id=n.conversation_id, author=getattr(n, 'author', None), body=n.body or "", created_at=ts))
    return out


@app.post("/api/conversations/{conv_id}/notes", response_model=NoteOut)
def create_note(conv_id: str, body: NoteCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if not body.body or not body.body.strip():
        raise HTTPException(status_code=400, detail="body-required")
    # Ensure table exists (best-effort in dev)
    try:
        Note.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    nid = str(uuid4())
    author = str(user.get("email") or user.get("sub") or "user")
    try:
        from datetime import datetime
        note = Note(id=nid, conversation_id=conv_id, author=author, body=body.body.strip(), created_at=datetime.utcnow())
        db.add(note)
        db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="note-store-failed")
    try:
        _audit(db, user, "note.created", "note", nid, {"conversation_id": conv_id})
    except Exception:
        pass
    return NoteOut(id=nid, conversation_id=conv_id, author=author, body=body.body.strip(), created_at=time.time())


@app.delete("/api/conversations/{conv_id}/notes/{note_id}")
def delete_note(conv_id: str, note_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    try:
        n = db.get(Note, note_id)
        if not n or n.conversation_id != conv_id:
            raise HTTPException(status_code=404, detail="note not found")
        db.delete(n)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="note-delete-failed")
    try:
        _audit(db, user, "note.deleted", "note", note_id, {"conversation_id": conv_id})
    except Exception:
        pass
    return {"ok": True}


# ----------------------------------------------------------------------------
# Webhook observability + test

class WebhookEventOut(BaseModel):
    id: str
    org_id: str
    wid: str | None = None
    type: str | None = None
    url: str | None = None
    ts: int | None = None


@app.get("/api/integrations/webhooks/events", response_model=list[WebhookEventOut])
def webhooks_events(kind: str = "delivered", limit: int = 50, user: dict = require_roles(Role.admin, Role.owner, Role.analyst)):
    stream = "wh:delivered" if kind == "delivered" else "nf:webhooks:dlq"
    try:
        raw = redis.xrevrange(stream, count=min(max(limit, 1), 200))
    except Exception:
        raw = []
    out: list[WebhookEventOut] = []
    for item in raw:
        try:
            _id, kv = item
        except Exception:
            continue
        if isinstance(kv, dict):
            m = {str(k): str(v) for k, v in kv.items()}
        else:
            # list-like alternating kv
            m = {}
            try:
                for i in range(0, len(kv), 2):
                    m[str(kv[i])] = str(kv[i+1])
            except Exception:
                m = {}
        if m.get("org_id") != str(user.get("org_id")):
            continue
        try:
            ts = int(m.get("ts") or 0)
        except Exception:
            ts = 0
        out.append(WebhookEventOut(id=str(_id.decode() if hasattr(_id, 'decode') else _id), org_id=str(m.get("org_id")), wid=m.get("wid"), type=m.get("type"), url=m.get("url"), ts=ts))
    return out


class WebhookTestIn(BaseModel):
    event_type: str | None = None
    payload: dict | None = None


@app.post("/api/integrations/webhooks/test")
def webhooks_test(body: WebhookTestIn, user: dict = require_roles(Role.admin, Role.owner)):
    evt = {
        "org_id": str(user.get("org_id")),
        "type": str(body.event_type or "webhook.test"),
        "event_id": str(uuid4()),
        "ts": str(int(time.time()*1000)),
        "body": json.dumps(body.payload or {"hello": "world"}),
    }
    try:
        redis.xadd("nf:webhooks", evt)
    except Exception:
        raise HTTPException(status_code=503, detail="webhook-test-enqueue-failed")
    return {"ok": True}


class WebhookRetryIn(BaseModel):
    id: str


@app.post("/api/integrations/webhooks/retry")
def webhooks_retry(body: WebhookRetryIn, user: dict = require_roles(Role.admin, Role.owner)):
    dlq = "nf:webhooks:dlq"
    try:
        rows = redis.xrange(dlq, min=body.id, max=body.id)
    except Exception:
        rows = []
    if not rows:
        raise HTTPException(status_code=404, detail="dlq-item-not-found")
    row = rows[0]
    _id, kv = row
    # normalize kv to dict[str,str]
    if isinstance(kv, dict):
        m = {str(k): str(v) for k, v in kv.items()}
    else:
        m = {}
        try:
            for i in range(0, len(kv), 2):
                m[str(kv[i])] = str(kv[i+1])
        except Exception:
            m = {}
    if m.get("org_id") != str(user.get("org_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    # requeue to nf:webhooks
    try:
        evt = {
            "org_id": m.get("org_id") or "",
            "type": m.get("type") or "event",
            "event_id": str(uuid4()),
            "ts": str(int(time.time()*1000)),
            "body": m.get("body") or "{}",
        }
        redis.xadd("nf:webhooks", evt)
        try:
            # best-effort delete from DLQ
            redis.xdel(dlq, _id)
        except Exception:
            pass
    except Exception:
        raise HTTPException(status_code=503, detail="webhook-retry-failed")
    return {"ok": True}


@app.get("/api/integrations/metrics")
def integrations_metrics(user: dict = require_roles(Role.admin, Role.owner, Role.analyst)):
    """Aggregate simple metrics for integrations and messaging components."""
    mgw_int = _fetch_mgw_metrics()
    wh_delivered = None
    wh_dlq = None
    incoming = None
    scheduled = None
    try:
        wh_delivered = redis.xlen("wh:delivered")
    except Exception:
        pass
    try:
        wh_dlq = redis.xlen("nf:webhooks:dlq")
    except Exception:
        pass
    try:
        incoming = redis.xlen("nf:incoming")
    except Exception:
        pass
    try:
        scheduled = redis.zcard(os.getenv("FLOW_ENGINE_SCHED_ZSET", "nf:incoming:scheduled"))
    except Exception:
        pass
    return {
        "messaging_gateway": mgw_int,
        "webhooks": {"delivered": wh_delivered, "dlq": wh_dlq},
        "engine": {"incoming": incoming, "scheduled": scheduled},
    }


# ----------------------------------------------------------------------------
# Attachments (by URL, MVP)

class AttachmentCreate(BaseModel):
    url: str | None = None
    filename: str | None = None
    storage_key: str | None = None


@app.get("/api/conversations/{conv_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(conv_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    try:
        Attachment.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    try:
        rows = db.query(Attachment).filter(Attachment.conversation_id == conv_id).order_by(getattr(Attachment, 'created_at', Attachment.id).desc()).all()
    except Exception:
        rows = []
    out: list[AttachmentOut] = []
    for a in rows:
        ts = None
        # If object stored via storage_key, generate presigned GET URL
        url = a.url or None
        try:
            if not url and getattr(a, 'storage_key', None):
                client = _minio_client()
                if client is not None:
                    url = client.presigned_get_object(MINIO_BUCKET, a.storage_key, expires=timedelta(minutes=10))
        except Exception:
            pass
        try:
            ts = a.created_at.timestamp() if getattr(a, 'created_at', None) else None
        except Exception:
            ts = None
        out.append(AttachmentOut(id=a.id, conversation_id=a.conversation_id, url=url or "", filename=getattr(a, 'filename', None), uploaded_by=getattr(a, 'uploaded_by', None), created_at=ts))
    return out


@app.post("/api/conversations/{conv_id}/attachments", response_model=AttachmentOut)
def create_attachment(conv_id: str, body: AttachmentCreate, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if (not body.url or not str(body.url).strip()) and (not body.storage_key or not str(body.storage_key).strip()):
        raise HTTPException(status_code=400, detail="url-or-storage_key-required")
    try:
        Attachment.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    aid = str(uuid4())
    uploader = str(user.get("email") or user.get("sub") or "user")
    try:
        from datetime import datetime
        row = Attachment(id=aid, conversation_id=conv_id, url=(str(body.url).strip() if body.url else None), filename=(body.filename or None), uploaded_by=uploader, created_at=datetime.utcnow(), storage_key=(str(body.storage_key).strip() if body.storage_key else None))
        db.add(row)
        db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="attachment-store-failed")
    try:
        _audit(db, user, "attachment.created", "attachment", aid, {"conversation_id": conv_id, "filename": body.filename, "storage_key": body.storage_key, "url": body.url})
    except Exception:
        pass
    # if storage_key, try to return presigned get url for convenience
    url_out = body.url
    try:
        if not url_out and body.storage_key:
            client = _minio_client()
            if client is not None:
                url_out = client.presigned_get_object(MINIO_BUCKET, body.storage_key, expires=timedelta(minutes=10))
    except Exception:
        pass
    return AttachmentOut(id=aid, conversation_id=conv_id, url=(url_out or ""), filename=(body.filename or None), uploaded_by=uploader, created_at=time.time())


@app.delete("/api/conversations/{conv_id}/attachments/{att_id}")
def delete_attachment(conv_id: str, att_id: str, user: dict = require_roles(Role.admin, Role.agent), db: Session = Depends(lambda: SessionLocal())):
    conv = _load_conv_for_org(db, conv_id, user.get("org_id"))
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    try:
        a = db.get(Attachment, att_id)
        if not a or a.conversation_id != conv_id:
            raise HTTPException(status_code=404, detail="attachment not found")
        db.delete(a)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="attachment-delete-failed")
    try:
        _audit(db, user, "attachment.deleted", "attachment", att_id, {"conversation_id": conv_id})
    except Exception:
        pass
    return {"ok": True}


# Presigned upload/download (MinIO/S3)
class UploadSignIn(BaseModel):
    filename: str
    content_type: str | None = None


class UploadSignOut(BaseModel):
    key: str
    url: str
    method: str = "PUT"


@app.post("/api/uploads/sign", response_model=UploadSignOut)
def sign_upload(body: UploadSignIn, user: dict = require_roles(Role.admin, Role.agent)):
    client = _minio_client()
    if client is None:
        raise HTTPException(status_code=501, detail="uploads-not-configured")
    # object key namespaced by org
    key = f"org={user.get('org_id')}/attachments/{int(time.time())}_{uuid4()}_{body.filename}"
    try:
        url = client.presigned_put_object(MINIO_BUCKET, key, expires=timedelta(minutes=10))
    except Exception:
        raise HTTPException(status_code=503, detail="sign-failed")
    return UploadSignOut(key=key, url=url)


# ----------------------------------------------------------------------------
# Audit (MVP)

class AuditLogOut(BaseModel):
    id: str
    org_id: str
    actor: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    data: dict | None = None
    created_at: float | None = None


@app.get("/api/audit", response_model=list[AuditLogOut])
def list_audit(
    limit: int = 100,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user: dict = require_roles(Role.admin),
    db: Session = Depends(lambda: SessionLocal()),
):
    # ensure table exists in dev
    try:
        AuditLog.__table__.create(bind=engine, checkfirst=True)  # type: ignore
    except Exception:
        pass
    try:
        q = db.query(AuditLog).filter(getattr(AuditLog, 'org_id') == str(user.get('org_id')))
        if action:
            q = q.filter(getattr(AuditLog, 'action') == action)
        if entity_type:
            q = q.filter(getattr(AuditLog, 'entity_type') == entity_type)
        if entity_id:
            q = q.filter(getattr(AuditLog, 'entity_id') == entity_id)
        # order by created_at desc when available
        order_col = getattr(AuditLog, 'created_at', None)
        if order_col is not None:
            q = q.order_by(order_col.desc())
        rows = q.limit(min(max(limit, 1), 500)).all()
    except Exception:
        rows = []
    out: list[AuditLogOut] = []
    for r in rows:
        ts = None
        try:
            ts = r.created_at.timestamp() if getattr(r, 'created_at', None) else None
        except Exception:
            ts = None
        out.append(
            AuditLogOut(
                id=r.id,
                org_id=r.org_id,
                actor=getattr(r, 'actor', None),
                action=r.action,
                entity_type=getattr(r, 'entity_type', None),
                entity_id=getattr(r, 'entity_id', None),
                data=getattr(r, 'data', None),
                created_at=ts,
            )
        )
    return out


@app.get("/api/audit/export")
def export_audit(
    format: str = "csv",
    limit: int = 1000,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user: dict = require_roles(Role.admin),
    db: Session = Depends(lambda: SessionLocal()),
):
    # reuse query from list_audit
    try:
        q = db.query(AuditLog).filter(getattr(AuditLog, 'org_id') == str(user.get('org_id')))
        if action:
            q = q.filter(getattr(AuditLog, 'action') == action)
        if entity_type:
            q = q.filter(getattr(AuditLog, 'entity_type') == entity_type)
        if entity_id:
            q = q.filter(getattr(AuditLog, 'entity_id') == entity_id)
        order_col = getattr(AuditLog, 'created_at', None)
        if order_col is not None:
            q = q.order_by(order_col.desc())
        rows = q.limit(min(max(limit, 1), 10000)).all()
    except Exception:
        rows = []
    items = []
    for r in rows:
        ts = None
        try:
            ts = r.created_at.isoformat() if getattr(r, 'created_at', None) else None
        except Exception:
            ts = None
        items.append({
            "id": r.id,
            "org_id": r.org_id,
            "actor": getattr(r, 'actor', None),
            "action": r.action,
            "entity_type": getattr(r, 'entity_type', None),
            "entity_id": getattr(r, 'entity_id', None),
            "data": json.dumps(getattr(r, 'data', None) or {}),
            "created_at": ts,
        })
    if (format or "").lower() == "json":
        return JSONResponse(items)
    # CSV
    import io, csv
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["id","org_id","actor","action","entity_type","entity_id","data","created_at"])
    w.writeheader()
    for it in items:
        w.writerow(it)
    data = buf.getvalue()
    return Response(content=data, media_type="text/csv")


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
    try:
        _audit(db, user, "conversation.messages.read", "conversation", conv_id, {"updated": int(updated), "up_to_id": body.up_to_id})
    except Exception:
        pass
    return {"updated": updated}

# ----------------------------------------------------------------------------
# Outgoing Webhooks (MVP)

class WebhookCreate(BaseModel):
    url: str
    secret: str | None = None
    events: list[str] | None = None  # e.g., ["message.sent","message.received","conversation.updated"]
    status: str | None = "active"


class WebhookOut(BaseModel):
    id: str
    url: str
    status: str | None = None
    events: list[str] | None = None
    created_at: float | None = None


def _wh_key(org_id: str) -> str:
    return f"wh:endpoints:{org_id}"


def _publish_webhook_event(org_id: str, event_type: str, payload: dict) -> None:
    try:
        evt = {
            "org_id": str(org_id),
            "type": str(event_type),
            "event_id": str(uuid4()),
            "ts": str(int(time.time() * 1000)),
            "body": json.dumps(payload),
        }
        redis.xadd("nf:webhooks", evt)
    except Exception:
        # best-effort; no crash on dev
        pass


@app.get("/api/integrations/webhooks", response_model=list[WebhookOut])
def webhooks_list(user: dict = require_roles(Role.admin),):
    org = str(user.get("org_id"))
    try:
        items = redis.hgetall(_wh_key(org)) or {}
    except Exception:
        items = {}
    out: list[WebhookOut] = []
    for wid, raw in items.items():
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"url": raw}
        out.append(WebhookOut(id=wid, url=str(obj.get("url")), status=obj.get("status"), events=obj.get("events"), created_at=obj.get("created_at")))
    return out


@app.post("/api/integrations/webhooks", response_model=WebhookOut)
def webhooks_create(body: WebhookCreate, user: dict = require_roles(Role.admin)):
    org = str(user.get("org_id"))
    wid = str(uuid4())
    obj = {
        "id": wid,
        "url": body.url,
        "secret": body.secret or "",
        "events": body.events or ["message.sent", "message.received", "conversation.updated"],
        "status": body.status or "active",
        "created_at": time.time(),
    }
    try:
        redis.hset(_wh_key(org), wid, json.dumps(obj))
    except Exception:
        raise HTTPException(status_code=503, detail="webhook-store-unavailable")
    try:
        # best-effort audit persist (use contacts DB if available)
        with SessionLocal() as db:
            _audit(db, user, "webhook.created", "webhook", wid, {"url": body.url, "events": obj["events"], "status": obj["status"]})
    except Exception:
        pass
    return WebhookOut(id=wid, url=obj["url"], status=obj["status"], events=obj["events"], created_at=obj["created_at"])


@app.delete("/api/integrations/webhooks/{wid}")
def webhooks_delete(wid: str, user: dict = require_roles(Role.admin)):
    org = str(user.get("org_id"))
    try:
        redis.hdel(_wh_key(org), wid)
    except Exception:
        pass
    try:
        with SessionLocal() as db:
            _audit(db, user, "webhook.deleted", "webhook", wid, None)
    except Exception:
        pass
    return {"ok": True}
# --- Workspaces --------------------------------------------------------------

@app.get("/api/my/workspaces", response_model=list[WorkspaceMembershipOut])
def list_my_workspaces(user: dict = Depends(current_user), db: Session = Depends(lambda: SessionLocal())):
    user_id = str(user.get("sub")) if user else ""
    if not user_id:
        return []
    memberships = _workspace_memberships_payload(db, user_id)
    return [WorkspaceMembershipOut(**item) for item in memberships]


@app.get("/api/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    rows = (
        db.query(Workspace)
        .filter(Workspace.org_id == user.get("org_id"))
        .order_by(getattr(Workspace, "created_at", Workspace.id))
        .all()
    )
    counts: dict[str, int] = {}
    if rows:
        ids = [ws.id for ws in rows]
        count_rows = (
            db.query(WorkspaceMember.workspace_id, func.count(WorkspaceMember.id))
            .filter(WorkspaceMember.workspace_id.in_(ids))
            .group_by(WorkspaceMember.workspace_id)
            .all()
        )
        counts = {wid: int(total) for wid, total in count_rows}
    out: list[WorkspaceOut] = []
    for ws in rows:
        out.append(WorkspaceOut(**_workspace_out(ws, counts.get(ws.id, 0))))
    return out


@app.post("/api/workspaces", response_model=WorkspaceOut)
def create_workspace(body: WorkspaceCreate, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="workspace-name-required")
    ws = Workspace(id=str(uuid4()), org_id=str(user.get("org_id")), name=name, created_at=datetime.utcnow())
    db.add(ws)
    db.commit()
    db.refresh(ws)
    try:
        _ensure_workspace_member(db, ws.id, str(user.get("sub")), "owner")
        _audit(db, user, "workspace.created", "workspace", ws.id, {"name": name})
    except Exception:
        pass
    return WorkspaceOut(**_workspace_out(ws, 1))


@app.put("/api/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: str, body: WorkspaceUpdate, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    updated = False
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="workspace-name-required")
        if ws.name != name:
            ws.name = name
            updated = True
    if updated:
        db.commit()
        db.refresh(ws)
        try:
            _audit(db, user, "workspace.updated", "workspace", ws.id, {"name": ws.name})
        except Exception:
            pass
    member_count = db.query(func.count(WorkspaceMember.id)).filter(WorkspaceMember.workspace_id == ws.id).scalar() or 0
    return WorkspaceOut(**_workspace_out(ws, member_count))


@app.delete("/api/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    total = db.query(Workspace).filter(Workspace.org_id == user.get("org_id")).count()
    if total <= 1:
        raise HTTPException(status_code=400, detail="workspace-delete-blocked-last")
    db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).delete()
    db.delete(ws)
    db.commit()
    try:
        _audit(db, user, "workspace.deleted", "workspace", workspace_id, None)
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
def list_workspace_members(workspace_id: str, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    rows = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id, isouter=True)
        .filter(WorkspaceMember.workspace_id == ws.id)
        .order_by(User.email.asc())
        .all()
    )
    out: list[WorkspaceMemberOut] = []
    for member, user_row in rows:
        out.append(WorkspaceMemberOut(**_workspace_member_out(member, user_row)))
    return out


@app.post("/api/workspaces/{workspace_id}/members", response_model=WorkspaceMemberOut)
def add_workspace_member(workspace_id: str, body: WorkspaceMemberCreate, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    target_user = db.get(User, body.user_id)
    if not target_user or str(target_user.org_id) != str(user.get("org_id")):
        raise HTTPException(status_code=404, detail="user-not-found")
    role = body.role if body.role in _WORKSPACE_MEMBER_ROLES else None
    if role is None:
        raise HTTPException(status_code=400, detail="workspace-role-invalid")
    member = _ensure_workspace_member(db, ws.id, target_user.id, role)
    try:
        _audit(db, user, "workspace.member.added", "workspace", ws.id, {"member_id": member.id, "role": member.role})
    except Exception:
        pass
    return WorkspaceMemberOut(**_workspace_member_out(member, target_user))


@app.put("/api/workspaces/{workspace_id}/members/{member_id}", response_model=WorkspaceMemberOut)
def update_workspace_member(workspace_id: str, member_id: str, body: WorkspaceMemberUpdate, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    member = db.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="member-not-found")
    role = body.role if body.role in _WORKSPACE_MEMBER_ROLES else None
    if role is None:
        raise HTTPException(status_code=400, detail="workspace-role-invalid")
    if member.role != role:
        member.role = role
        db.commit()
        db.refresh(member)
        try:
            _audit(db, user, "workspace.member.updated", "workspace", ws.id, {"member_id": member.id, "role": member.role})
        except Exception:
            pass
    target_user = db.get(User, member.user_id)
    return WorkspaceMemberOut(**_workspace_member_out(member, target_user))


@app.delete("/api/workspaces/{workspace_id}/members/{member_id}")
def delete_workspace_member(workspace_id: str, member_id: str, user: dict = require_roles(Role.owner, Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ws = _load_workspace_for_org(db, workspace_id, user.get("org_id"))
    if not ws:
        raise HTTPException(status_code=404, detail="workspace-not-found")
    member = db.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="member-not-found")
    db.delete(member)
    db.commit()
    try:
        _audit(db, user, "workspace.member.deleted", "workspace", ws.id, {"member_id": member.id})
    except Exception:
        pass
    return {"ok": True}

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
    try:
        _audit(db, user, "channel.created", "channel", ch.id, {"type": ch.type, "mode": ch.mode, "phone_number": ch.phone_number})
    except Exception:
        pass
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=_sanitize_credentials(ch.credentials))


@app.get("/api/channels", response_model=list[ChannelOut])
def list_channels(user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    rows = db.query(Channel).filter(Channel.org_id == user.get("org_id")).all()
    return [ChannelOut(id=r.id, org_id=r.org_id, type=r.type, mode=r.mode, status=r.status, phone_number=r.phone_number, credentials=_sanitize_credentials(r.credentials)) for r in rows]


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
def get_channel(ch_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=_sanitize_credentials(ch.credentials))


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
        try:
            current = ch.credentials or {}
            if not isinstance(current, dict):
                current = {}
            for k, v in (body.credentials or {}).items():
                if v is None:
                    # allow clearing keys explicitly
                    current.pop(k, None)
                else:
                    current[k] = v
            ch.credentials = current
        except Exception:
            ch.credentials = body.credentials
    db.commit()
    db.refresh(ch)
    try:
        _audit(db, user, "channel.updated", "channel", ch.id, {"status": ch.status, "phone_number": ch.phone_number})
    except Exception:
        pass
    return ChannelOut(id=ch.id, org_id=ch.org_id, type=ch.type, mode=ch.mode, status=ch.status, phone_number=ch.phone_number, credentials=_sanitize_credentials(ch.credentials))


@app.delete("/api/channels/{ch_id}")
def delete_channel(ch_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    db.delete(ch)
    db.commit()
    try:
        _audit(db, user, "channel.deleted", "channel", ch_id, None)
    except Exception:
        pass
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
def verify_channel(ch_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
    ch = _load_channel_for_org(db, ch_id, user.get("org_id"))
    if not ch:
        raise HTTPException(status_code=404, detail="channel not found")
    creds = getattr(ch, "credentials", None) or {}
    pnid = _get_pnid(creds)
    access_token = None
    try:
        access_token = creds.get("access_token") if isinstance(creds, dict) else None
    except Exception:
        access_token = None

    # Prefer direct verification against Graph if credentials are provided for this channel
    ok = False
    status = None
    phone_id = None
    if pnid and access_token:
        ok, status, phone_id = _verify_wa_cloud_phone_id(pnid, access_token)
        if ok:
            return ChannelVerifyOut(ok=True, status="ok", fake=False, has_token=True, phone_id=phone_id or pnid, match=True, details=None)
        # If direct check failed, fall back to MGW internal status as a softer signal

    st = _fetch_mgw_status()
    if st is None:
        return ChannelVerifyOut(ok=False, status="warning", details=(status or "messaging-gateway unreachable"))
    try:
        info = (((st or {}).get("workers", {}) or {}).get("send_worker", {}) or {})
        fake = bool(info.get("fake"))
        has_token = bool(info.get("has_token")) or bool(access_token)
        mgw_phone_id = info.get("phone_id")
        match = (pnid is None) or (mgw_phone_id == pnid)
        ok2 = match and (has_token or fake)
        out_status = "ok" if ok2 else "warning"
        details = None if ok2 else (status or ("phone_id mismatch" if pnid and mgw_phone_id and mgw_phone_id != pnid else "missing token or phone_id"))
        if ok2 and fake:
            details = "fake-mode"
        return ChannelVerifyOut(ok=ok2, status=out_status, fake=fake, has_token=has_token, phone_id=mgw_phone_id or phone_id or pnid, match=match, details=details)
    except Exception:
        return ChannelVerifyOut(ok=False, status="error", details=status or "invalid mgw status format")


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
    try:
        _audit(db, user, "template.created", "template", tid, {"name": body.name, "language": body.language})
    except Exception:
        pass
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
def list_templates(user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
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
def get_template(tpl_id: str, user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
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
    try:
        _audit(db, user, "template.updated", "template", tpl_id, {"status": r.status})
    except Exception:
        pass
    return TemplateOut(id=r.id, org_id=r.org_id, name=r.name, language=r.language, category=r.category, body=r.body, variables=r.variables, status=r.status)


@app.delete("/api/templates/{tpl_id}")
def delete_template(tpl_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_template_for_org(db, tpl_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="template not found")
    db.delete(r)
    db.commit()
    try:
        _audit(db, user, "template.deleted", "template", tpl_id, None)
    except Exception:
        pass
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
def list_flows(user: dict = require_roles(Role.admin, Role.agent, Role.owner, Role.analyst), db: Session = Depends(lambda: SessionLocal())):
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
    try:
        _audit(db, user, "flow.created", "flow", fid, {"name": body.name, "status": body.status or "draft"})
    except Exception:
        pass
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
    try:
        _audit(db, user, "flow.updated", "flow", flow_id, {"status": r.status, "version": r.version})
    except Exception:
        pass
    return FlowOut(id=r.id, org_id=r.org_id, name=r.name, version=r.version, graph=r.graph if isinstance(r.graph, dict) else None, status=r.status, created_by=r.created_by)


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: str, user: dict = require_roles(Role.admin), db: Session = Depends(lambda: SessionLocal())):
    r = _load_flow_for_org(db, flow_id, user.get("org_id"))
    if not r:
        raise HTTPException(status_code=404, detail="flow not found")
    db.delete(r)
    db.commit()
    try:
        _audit(db, user, "flow.deleted", "flow", flow_id, None)
    except Exception:
        pass
    return {"ok": True}

# ----------------------------------------------------------------------------
# Contacts (CRUD + simple search) - mirrors services/contacts for convenience

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






