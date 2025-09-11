import os, json, time, asyncio, logging, uuid
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

def classify_intent(text: str) -> str:
	t = (text or "").lower()
	if "precio" in t or "costo" in t or "precio" in t:
		return "pricing"
	if "hola" in t or "buenas" in t:
		return "greeting"
	return "default"

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
        intent = classify_intent(text)
        # simple action: reply with a template based on intent
        if intent == "pricing":
            reply = f"Gracias por preguntar sobre precios. Nuestro plan starter cuesta $9/mes."
        elif intent == "greeting":
            reply = "Hola! ¿En qué puedo ayudarte hoy?"
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
    - Map classify_intent(text) -> path name; default to "default" or first key.
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

    path_key = None
    if resume and resume.get("path"):
        path_key = resume.get("path")
    elif mapping:
        it = classify_intent(text)
        path_key = mapping.get(it) or mapping.get("default")
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
                context={"intent": classify_intent(text)},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            with SessionLocal() as db:
                db.add(run)
                db.commit()
    except Exception:
        logger.exception("flow_run persist failed")
    return outputs

async def _schedule_resume(fields: dict, payload: dict, path_key: str, next_index: int, delay_seconds: int, contact_phone: str | None):
    try:
        due_at = int(time.time()) + int(delay_seconds)
        item = {
            "payload": json.dumps(payload),
            "org_id": fields.get("org_id") or "",
            "channel_id": fields.get("channel_id") or "wa_main",
            # stash contact phone to avoid re-parsing webhook payload later
            "contact_phone": contact_phone or "",
            "engine_resume": json.dumps({"path": path_key, "index": next_index}),
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
