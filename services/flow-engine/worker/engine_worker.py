import os, json, time, asyncio, logging, uuid, re
import httpx
from prometheus_client import Counter, start_http_server
from pythonjsonlogger import json as jsonlogger
from redis import Redis

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger("engine_worker")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Metrics (opt-in via env var to avoid duplicate registration in tests)
_METRICS_ENABLED = os.getenv("FLOW_ENGINE_METRICS", "false").lower() == "true"
CONSUMER_GROUP = os.getenv("FLOW_ENGINE_GROUP", "engine")
CONSUMER_NAME = os.getenv("FLOW_ENGINE_CONSUMER", None) or os.getenv("HOSTNAME", "engine-1")
try:
    ENGINE_MAX_RETRIES = int(os.getenv("FLOW_ENGINE_MAX_RETRIES", "2"))
except Exception:
    ENGINE_MAX_RETRIES = 2
try:
    _SCHED_POLL_MS = int(os.getenv("FLOW_ENGINE_SCHED_POLL_MS", "500"))
except Exception:
    _SCHED_POLL_MS = 500
_SCHED_ZSET = os.getenv("FLOW_ENGINE_SCHED_ZSET", "nf:incoming:scheduled")
_WAIT_PREFIX = os.getenv("FLOW_ENGINE_WAIT_PREFIX", "fe:wait")

_NLP_SERVICE_URL = os.getenv("NLP_SERVICE_URL", "http://nlp:8000").rstrip("/")
try:
    _NLP_TIMEOUT = float(os.getenv("NLP_TIMEOUT_SECONDS", "1.5"))
except Exception:
    _NLP_TIMEOUT = 1.5
_INTENT_DEFAULT = os.getenv("NLP_FALLBACK_INTENT", "default")
_INTENT_WARNED = False

class _Noop:
    def inc(self, *args, **kwargs):
        return None

if _METRICS_ENABLED:
    ENGINE_PROCESSED = Counter('nexia_engine_incoming_processed_total', 'Incoming messages processed')
    ENGINE_PUBLISHED = Counter('nexia_engine_outbox_published_total', 'Actions published to nf:outbox')
    ENGINE_ERRORS = Counter('nexia_engine_errors_total', 'Engine errors')
    ENGINE_RETRIED = Counter('nexia_engine_retries_total', 'Engine message retries')
    ENGINE_DLQ = Counter('nexia_engine_dlq_total', 'Engine DLQ messages')
    ENGINE_SCHEDULED = Counter('nexia_engine_scheduled_total', 'Flow events scheduled for later')
    ENGINE_SCHED_PUBLISHED = Counter('nexia_engine_sched_published_total', 'Scheduled events published back to nf:incoming')
else:
    ENGINE_PROCESSED = _Noop()
    ENGINE_PUBLISHED = _Noop()
    ENGINE_ERRORS = _Noop()
    ENGINE_RETRIED = _Noop()
    ENGINE_DLQ = _Noop()
    ENGINE_SCHEDULED = _Noop()
    ENGINE_SCHED_PUBLISHED = _Noop()

try:
    from packages.common.db import SessionLocal  # type: ignore
    from packages.common.models import Flow as DBFlow, FlowRun as DBFlowRun, Contact as DBContact  # type: ignore
except Exception:
    SessionLocal = None  # type: ignore
    DBFlow = None  # type: ignore
    DBFlowRun = None  # type: ignore
    DBContact = None  # type: ignore

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
        try:
            ENGINE_ERRORS.inc()
        except Exception:
            pass
        return None

def _fallback_intent(text: str) -> str:
    t = (text or "").lower()
    if "precio" in t or "costo" in t or "plan" in t or "tarifa" in t:
        return "pricing"
    if "hola" in t or "buenas" in t or "buenos" in t:
        return "greeting"
    if "soporte" in t or "ayuda" in t or "problema" in t or "error" in t:
        return "support"
    if "humano" in t or "asesor" in t or "agente" in t:
        return "handoff"
    return _INTENT_DEFAULT


async def classify_intent(text: str) -> str:
    message = (text or "").strip()
    if not message:
        return _INTENT_DEFAULT
    if not _NLP_SERVICE_URL:
        return _fallback_intent(message)

    global _INTENT_WARNED
    url = f"{_NLP_SERVICE_URL}/api/nlp/intents"
    payload = {"text": message, "top_k": 1}
    try:
        async with httpx.AsyncClient(timeout=_NLP_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                primary = data.get("primary_intent") or data.get("top_intents", [{}])[0].get("label")
                if isinstance(primary, str) and primary:
                    return primary.strip().lower()
            else:
                if not _INTENT_WARNED:
                    logger.warning("nlp service returned %s", resp.status_code)
                    _INTENT_WARNED = True
    except Exception:
        if not _INTENT_WARNED:
            logger.exception("nlp intent classification failed")
            _INTENT_WARNED = True
    return _fallback_intent(message)

async def handle_message(msg_id: str, fields: dict) -> bool:
    payload_raw = fields.get("payload") or fields.get("body") or ""
    try:
        payload = json.loads(payload_raw)
    except Exception:
        payload = {"text": payload_raw}
    # try to extract text from common WA structure
    text = ""
    # also try to extract contact phone (for replies)
    contact_phone = None
    # Common webhook path: entry->[0]->changes->[0]->value->messages->[0]->text->body
    try:
        entry = payload.get("entry", [])
        if entry:
            changes = entry[0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    m0 = messages[0]
                    text = m0.get("text", {}).get("body", "")
                    # for WhatsApp Cloud incoming, the sender's phone is in `from`
                    contact_phone = m0.get("from") or contact_phone
                # also check value.contacts[0].wa_id if present
                contacts = value.get("contacts", [])
                if contacts:
                    contact_phone = contacts[0].get("wa_id") or contact_phone
    except Exception:
        pass
    if not text:
        # fallback to a top-level text
        text = payload.get("text") or payload.get("message") or ""

    # If there's a waiting rule for this contact, check match and optionally resume
    org_id = fields.get("org_id")
    channel_id = fields.get("channel_id") or "wa_main"
    waited = False
    if org_id and (contact_phone or payload.get("contact", {}).get("phone")):
        target_phone = contact_phone or payload.get("contact", {}).get("phone")
        wkey = f"{_WAIT_PREFIX}:{org_id}:{channel_id}:{target_phone}"
        try:
            raw = redis.get(wkey)
        except Exception:
            raw = None
        if raw:
            waited = True
            try:
                cfg = json.loads(raw)
            except Exception:
                cfg = None
            matched = True
            patt = None
            try:
                patt = cfg.get("pattern") if isinstance(cfg, dict) else None
            except Exception:
                patt = None
            if patt:
                try:
                    matched = bool(re.search(str(patt), text or "", re.IGNORECASE))
                except Exception:
                    matched = False
            if matched and isinstance(cfg, dict):
                # clear wait and resume flow at stored path/index
                try:
                    redis.delete(wkey)
                except Exception:
                    pass
                resume = {"path": cfg.get("path"), "index": int(cfg.get("index") or 0)}
                fields["engine_resume"] = json.dumps(resume)
            else:
                # still waiting: suppress default replies
                return True

    # Try to run a configured flow; fall back to heuristic reply
    published = False
    try:
        outs = await _run_flow_minimal(text=text, contact_phone=contact_phone, fields=fields, payload=payload)
        for out in outs:
            # ensure minimal enrichment
            if fields.get("org_id"):
                out["org_id"] = fields.get("org_id")
            trace_id = out.get("trace_id") or str(uuid.uuid4())
            out["trace_id"] = trace_id
            redis.xadd("nf:outbox", {k: str(v) for k, v in out.items()})
            try:
                ENGINE_PUBLISHED.inc()
            except Exception:
                pass
            logger.info("published nf:outbox message", extra={"trace_id": trace_id, "to": out.get("to"), "client_id": out.get("client_id")})
            published = True
    except Exception:
        logger.exception("flow execution failed")
        try:
            ENGINE_ERRORS.inc()
        except Exception:
            pass

    if not published:
        intent = await classify_intent(text)
        # simple action: reply with a template based on intent
        if intent == "pricing":
            reply = "Gracias por preguntar sobre precios. Nuestro plan starter cuesta $9/mes."
        elif intent == "greeting":
            reply = "Hola! ¿En qué puedo ayudarte hoy?"
        elif intent == "support":
            reply = "Veo que necesitas ayuda. Un agente se pondrá en contacto contigo en breve."
        else:
            reply = "Gracias por tu mensaje. Un agente te responderá pronto."

        # publish to outbox (so messaging-gateway will pick it)
        # include org_id/channel_id when provided by upstream (webhook enrichment)
        try:
            trace_id = str(uuid.uuid4())
            channel = fields.get("channel_id") or "wa_main"
            to_phone = contact_phone or payload.get("contact", {}).get("phone", "unknown")
            out = {
                "channel_id": channel,
                "to": to_phone,
                "type": "text",
                "text": reply,
                "client_id": f"auto_{int(time.time()*1000)}",
                "orig_text": text,
                "trace_id": trace_id,
            }
            if fields.get("org_id"):
                out["org_id"] = fields.get("org_id")
            # ensure all values are strings for redis stream
            redis.xadd("nf:outbox", {k: str(v) for k, v in out.items()})
            try:
                ENGINE_PUBLISHED.inc()
            except Exception:
                pass
            # log the published message with trace_id for observability
            logger.info("published nf:outbox message", extra={"trace_id": trace_id, "to": out.get("to"), "client_id": out.get("client_id")})
        except Exception:
            logger.exception("engine xadd failed")
            try:
                ENGINE_ERRORS.inc()
            except Exception:
                pass
            return False
        return True
    return True

async def _run_flow_minimal(text: str, contact_phone: str | None, fields: dict, payload: dict) -> list[dict]:
    """Execute a very small subset of a flow definition if available.

    Strategy:
    - Look up latest active flow for org_id (if org_id present).
    - Find first node with type "intent" and a "map" dict.
    - Map await classify_intent(text) -> path name; default to "default" or first key.
    - Execute first step of that path if it's an action of type send_*.
    - Return list of 0..N outbox messages to publish.
    """
    org_id = fields.get("org_id")
    if not org_id or not SessionLocal or not DBFlow:
        return []
    try:
        with SessionLocal() as db:
            # Prefer latest active/published flow
            row = (
                db.query(DBFlow)
                .filter(getattr(DBFlow, "org_id") == str(org_id))
                .filter(getattr(DBFlow, "status") == "active")
                .order_by(getattr(DBFlow, "version", 0).desc())
                .first()
            )
    except Exception:
        row = None
    if not row:
        return []
    graph = getattr(row, "graph", None)
    if not isinstance(graph, dict):
        return []
    mapping = None
    try:
        for n in graph.get("nodes", []) or []:
            if n.get("type") == "intent" and isinstance(n.get("map"), dict):
                mapping = n.get("map")
                break
    except Exception:
        mapping = None
    # Support resume from scheduled step
    resume = None
    try:
        if fields.get("engine_resume"):
            resume = json.loads(fields.get("engine_resume")) if isinstance(fields.get("engine_resume"), str) else fields.get("engine_resume")
    except Exception:
        resume = None

    intent_label = await classify_intent(text)
    path_key = None
    if resume and resume.get("path"):
        path_key = resume.get("path")
    elif mapping:
        path_key = mapping.get(intent_label) or mapping.get("default")
    # Fallback: try a well-known path
    if not path_key:
        path_key = "path_default"
    steps = None
    try:
        steps = (graph.get("paths", {}) or {}).get(path_key)
    except Exception:
        steps = None
    if not isinstance(steps, list) or not steps:
        return []
    # Execute multiple consecutive steps (MVP: up to 5)
    channel = fields.get("channel_id") or "wa_main"
    to_phone = contact_phone or payload.get("contact", {}).get("phone", "unknown")
    base = {
        "channel_id": channel,
        "to": to_phone,
        "client_id": f"auto_{int(time.time()*1000)}",
        "orig_text": text,
    }
    outputs: list[dict] = []
    start_index = 0
    try:
        if resume and isinstance(resume.get("index"), int):
            start_index = max(0, int(resume["index"]))
    except Exception:
        start_index = 0
    for idx, step in enumerate(steps[start_index:start_index+5], start=start_index):
        if not isinstance(step, dict):
            break
        stype = step.get("type")
        if stype == "wait_for_reply":
            # Store a waiting rule for this contact and schedule an optional timeout resume
            pattern = step.get("pattern")
            seconds = 0
            try:
                seconds = int(step.get("seconds") or step.get("timeout_seconds") or 0)
            except Exception:
                seconds = 0
            resume_token = str(uuid.uuid4())
            # Next index to continue when reply arrives
            next_index = idx + 1
            # Optionally a timeout path (start at 0)
            timeout_path = step.get("timeout_path")
            # Persist wait state with TTL
            try:
                wkey = f"{_WAIT_PREFIX}:{org_id}:{channel}:{to_phone}"
                record = {
                    "path": path_key,
                    "index": next_index,
                    "pattern": pattern,
                    "resume_token": resume_token,
                    "org_id": str(org_id or ""),
                    "channel_id": channel,
                    "contact_phone": to_phone,
                    "timeout_path": timeout_path,
                }
                redis.set(wkey, json.dumps(record), ex=max(1, seconds or 3600))
            except Exception:
                logger.exception("failed to set wait state")
            # Schedule a timeout resume when seconds > 0
            if seconds and seconds > 0:
                try:
                    if timeout_path:
                        await _schedule_resume(fields=fields, payload=payload, path_key=timeout_path, next_index=0, delay_seconds=seconds, contact_phone=contact_phone, resume_token=resume_token)
                    else:
                        await _schedule_resume(fields=fields, payload=payload, path_key=path_key, next_index=next_index, delay_seconds=seconds, contact_phone=contact_phone, resume_token=resume_token)
                except Exception:
                    logger.exception("schedule timeout for wait_for_reply failed")
            # Stop processing further steps now
            break
        if stype == "set_attribute":
            # Update contact.attributes[key] = value (best-effort)
            key = step.get("key")
            val = step.get("value")
            if key and SessionLocal and DBContact and org_id and (contact_phone or payload.get("contact", {}).get("phone")):
                target = contact_phone or payload.get("contact", {}).get("phone")
                try:
                    with SessionLocal() as db:
                        ct = (
                            db.query(DBContact)
                            .filter(getattr(DBContact, 'org_id') == str(org_id))
                            .filter((getattr(DBContact, 'wa_id') == target) | (getattr(DBContact, 'phone') == target))
                            .first()
                        )
                        if ct is not None:
                            attrs = getattr(ct, 'attributes', None) or {}
                            attrs[str(key)] = val
                            ct.attributes = attrs
                            db.commit()
                except Exception:
                    logger.exception("set_attribute failed")
            # continue to next step
            continue
        if stype in ("wait", "delay"):
            # schedule resume at idx+1
            seconds = 0
            try:
                seconds = int(step.get("seconds") or step.get("sec") or step.get("ms", 0) / 1000)
            except Exception:
                seconds = 0
            await _schedule_resume(fields=fields, payload=payload, path_key=path_key, next_index=idx+1, delay_seconds=max(0, seconds), contact_phone=contact_phone)
            # stop further processing now
            break
        if stype != "action":
            break
        act = step.get("action")
        if act == "send_text":
            txt = step.get("text") or "Gracias por tu mensaje."
            outputs.append({**base, "type": "text", "text": txt})
        elif act == "send_template":
            name = step.get("template") or "welcome"
            lang = step.get("language") or {"code": "es"}
            tpl = {"name": name, "language": lang, "components": step.get("components") or []}
            outputs.append({**base, "type": "template", "template": json.dumps(tpl)})
        elif act == "send_media":
            media = step.get("media") or {"kind": "image", "link": step.get("asset") or "https://example.com/demo.jpg"}
            outputs.append({**base, "type": "media", "media": json.dumps(media)})
        elif act == "webhook":
            # Publish a flow webhook event for external systems (best-effort)
            try:
                evt = {
                    "org_id": str(org_id or ""),
                    "type": "flow.webhook",
                    "event_id": str(uuid.uuid4()),
                    "ts": str(int(time.time() * 1000)),
                    "body": json.dumps({
                        "flow_id": getattr(row, 'id', None),
                        "path": path_key,
                        "step_index": idx,
                        "data": step.get("data") or step.get("payload") or {},
                        "input_text": text,
                        "contact_phone": to_phone,
                        "channel_id": channel,
                    }),
                }
                redis.xadd("nf:webhooks", evt)
            except Exception:
                logger.exception("flow webhook publish failed")
            # continue chain
            continue
        else:
            # unsupported action -> stop
            break
    # Persist a minimal run record (best-effort)
    try:
        if SessionLocal and DBFlowRun and row is not None:
            from datetime import datetime
            run = DBFlowRun(
                id=str(uuid.uuid4()),
                org_id=str(org_id),
                flow_id=getattr(row, 'id', None),
                status='completed' if outputs else 'running',
                last_step=str(path_key),
                context={"intent": intent_label or _INTENT_DEFAULT},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            with SessionLocal() as db:
                db.add(run)
                db.commit()
    except Exception:
        logger.exception("flow_run persist failed")
    return outputs

async def _schedule_resume(fields: dict, payload: dict, path_key: str, next_index: int, delay_seconds: int, contact_phone: str | None, resume_token: str | None = None):
    try:
        due_at = int(time.time()) + int(delay_seconds)
        item = {
            "payload": json.dumps(payload),
            "org_id": fields.get("org_id") or "",
            "channel_id": fields.get("channel_id") or "wa_main",
            # stash contact phone to avoid re-parsing webhook payload later
            "contact_phone": contact_phone or "",
            "engine_resume": json.dumps({"path": path_key, "index": next_index}),
            **({"resume_token": resume_token} if resume_token else {}),
        }
        redis.zadd(_SCHED_ZSET, {json.dumps(item): due_at})
        try:
            ENGINE_SCHEDULED.inc()
        except Exception:
            pass
        logger.info("scheduled resume in %ss for path=%s index=%s", delay_seconds, path_key, next_index)
    except Exception:
        logger.exception("schedule failed")

async def _ensure_group(stream: str, group: str):
    try:
        # MKSTREAM to create if missing
        await asyncio.to_thread(redis.execute_command, 'XGROUP', 'CREATE', stream, group, '$', 'MKSTREAM')
        logger.info("created consumer group %s on %s", group, stream)
    except Exception as e:
        # group exists or race
        if "BUSYGROUP" in str(e).upper():
            return
        # ignore other errors in dev
        return


async def loop():
    stream = 'nf:incoming'
    await _ensure_group(stream, CONSUMER_GROUP)
    logger.info("engine_worker starting (group=%s consumer=%s)", CONSUMER_GROUP, CONSUMER_NAME)
    while True:
        try:
            raw = await asyncio.to_thread(
                redis.execute_command,
                'XREADGROUP', 'GROUP', CONSUMER_GROUP, CONSUMER_NAME,
                'BLOCK', 5000, 'COUNT', 1, 'STREAMS', stream, '>'
            )
            if not raw:
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
                        logger.exception("engine_worker failed parsing XREADGROUP fields")
                        # ack to avoid poison in dev
                        try:
                            redis.xack(stream, CONSUMER_GROUP, msg_id)
                        except Exception:
                            pass
                        continue
                    ok = await handle_message(msg_id, fields)
                    try:
                        ENGINE_PROCESSED.inc()
                    except Exception:
                        pass
                    if ok:
                        try:
                            redis.xack(stream, CONSUMER_GROUP, msg_id)
                        except Exception:
                            logger.exception("xack failed")
                    else:
                        # retry or DLQ
                        retries = 0
                        try:
                            retries = int(fields.get("retries", "0"))
                        except Exception:
                            retries = 0
                        if retries < ENGINE_MAX_RETRIES:
                            fields["retries"] = str(retries + 1)
                            try:
                                redis.xadd(stream, {k: str(v) for k, v in fields.items()})
                                ENGINE_RETRIED.inc()
                            except Exception:
                                logger.exception("requeue failed")
                            # ack original regardless to avoid poison
                            try:
                                redis.xack(stream, CONSUMER_GROUP, msg_id)
                            except Exception:
                                pass
                        else:
                            # send to DLQ
                            try:
                                dlq = {**fields, "error": "max-retries-exceeded"}
                                redis.xadd('nf:incoming:dlq', {k: str(v) for k, v in dlq.items()})
                                ENGINE_DLQ.inc()
                            except Exception:
                                logger.exception("dlq publish failed")
                            try:
                                redis.xack(stream, CONSUMER_GROUP, msg_id)
                            except Exception:
                                pass
        except Exception:
            logger.exception("engine error")
            try:
                ENGINE_ERRORS.inc()
            except Exception:
                pass
            await asyncio.sleep(1)


async def scheduler_loop():
    logger.info("flow scheduler starting (poll=%sms zset=%s)", _SCHED_POLL_MS, _SCHED_ZSET)
    while True:
        try:
            now = int(time.time())
            # fetch small batches of due items
            items = redis.zrangebyscore(_SCHED_ZSET, '-inf', now, start=0, num=10)
            if not items:
                await asyncio.sleep(_SCHED_POLL_MS / 1000.0)
                continue
            for raw in items:
                # attempt to claim by removing; if removed==1 we own it
                removed = redis.zrem(_SCHED_ZSET, raw)
                if not removed:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = None
                if not isinstance(obj, dict):
                    continue
                # Skip if waiting state cleared or token mismatch (reply already arrived)
                try:
                    if obj.get("resume_token"):
                        wkey = f"{_WAIT_PREFIX}:{obj.get('org_id') or ''}:{obj.get('channel_id') or 'wa_main'}:{obj.get('contact_phone') or ''}"
                        raw_state = redis.get(wkey)
                        if not raw_state:
                            # already handled or expired
                            continue
                        st = json.loads(raw_state)
                        if st.get("resume_token") != obj.get("resume_token"):
                            continue
                        # clear state on timeout resume
                        try:
                            redis.delete(wkey)
                        except Exception:
                            pass
                except Exception:
                    logger.exception("wait state check failed")
                mapping = {
                    "payload": obj.get("payload") or "",
                    "org_id": obj.get("org_id") or "",
                    "channel_id": obj.get("channel_id") or "wa_main",
                    "engine_resume": obj.get("engine_resume") or "",
                }
                # also pass through contact_phone for faster resolution
                if obj.get("contact_phone"):
                    mapping["contact_phone"] = obj.get("contact_phone")
                try:
                    redis.xadd('nf:incoming', mapping)
                    try:
                        ENGINE_SCHED_PUBLISHED.inc()
                    except Exception:
                        pass
                except Exception:
                    logger.exception("scheduler publish failed")
        except Exception:
            logger.exception("scheduler loop error")
            await asyncio.sleep(1)

if __name__ == "__main__":
    # Start metrics HTTP server if a port is provided
    try:
        port = int(os.getenv("FLOW_ENGINE_METRICS_PORT", "0") or 0)
        if port > 0 and _METRICS_ENABLED:
            start_http_server(port)
    except Exception:
        pass
    async def _main():
        await asyncio.gather(loop(), scheduler_loop())
    asyncio.run(_main())
