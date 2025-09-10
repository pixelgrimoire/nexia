import os, asyncio, time, logging, uuid, json

import httpx
from pythonjsonlogger import json as jsonlogger
from redis import Redis
from packages.common.db import SessionLocal
from packages.common.models import Message as DBMessage, Conversation as DBConversation, Contact as DBContact

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
FAKE = os.getenv("WHATSAPP_FAKE_MODE", "true").lower() == "true"
TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger("send_worker")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

async def process_message(msg_id: str, fields: dict):
    to = fields.get("to")
    text = fields.get("text") or (fields.get("body") or "")
    client_id = fields.get("client_id")
    msg_type = fields.get("type") or "text"
    tpl_obj = None
    media_obj = None
    if msg_type == "template" and fields.get("template"):
        try:
            tpl_obj = json.loads(fields.get("template")) if isinstance(fields.get("template"), str) else fields.get("template")
        except Exception:
            tpl_obj = None
    if msg_type == "media" and fields.get("media"):
        try:
            media_obj = json.loads(fields.get("media")) if isinstance(fields.get("media"), str) else fields.get("media")
        except Exception:
            media_obj = None
    if FAKE:
        result = {"fake": True, "to": to, "text": text, "client_id": client_id, "ts": time.time()}
        if fields.get('orig_text'):
            result['orig_text'] = fields.get('orig_text')
        if fields.get('trace_id'):
            result['trace_id'] = fields.get('trace_id')
        if fields.get('org_id'):
            result['org_id'] = fields.get('org_id')
        if fields.get('channel_id'):
            result['channel_id'] = fields.get('channel_id')
        if msg_type == 'template' and tpl_obj:
            result['template_name'] = tpl_obj.get('name')
        if msg_type == 'media' and media_obj:
            result['media_kind'] = media_obj.get('kind')
    else:
        url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        payload = {"messaging_product": "whatsapp", "to": to}
        if msg_type == "template" and tpl_obj:
            payload["type"] = "template"
            payload["template"] = tpl_obj
        elif msg_type == "media" and media_obj:
            kind = media_obj.get("kind")
            link = media_obj.get("link")
            caption = media_obj.get("caption")
            payload["type"] = kind
            payload[kind] = {"link": link}
            if caption:
                payload[kind]["caption"] = caption
        else:
            payload["type"] = "text"
            payload["text"] = {"body": text}
        wa_msg_id = None
        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    httpx.post, url, headers=headers, json=payload, timeout=10
                )
                logger.info("whatsapp %s %s", resp.status_code, resp.text)
                resp.raise_for_status()
                wa_msg_id = resp.json().get("messages", [{}])[0].get("id")
                # increment WhatsApp call counter
                try:
                    redis.incr("mgw:metrics:wa_calls_total")
                except Exception:
                    pass
                break
            except Exception:
                logger.exception("whatsapp send attempt %s failed", attempt + 1)
                try:
                    redis.incr("mgw:metrics:errors_total")
                except Exception:
                    pass
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        result = {"fake": False, "to": to, "text": text, "client_id": client_id, "ts": time.time()}
        if wa_msg_id:
            result["wa_msg_id"] = wa_msg_id
        if fields.get('orig_text'):
            result['orig_text'] = fields.get('orig_text')
        if fields.get('trace_id'):
            result['trace_id'] = fields.get('trace_id')
        if fields.get('org_id'):
            result['org_id'] = fields.get('org_id')
        if fields.get('channel_id'):
            result['channel_id'] = fields.get('channel_id')
    try:
        # ensure all values are strings for redis stream
        redis.xadd("nf:sent", {k: str(v) for k, v in result.items()})
    except Exception:
        logger.exception("send_worker xadd error")
        try:
            redis.incr("mgw:metrics:errors_total")
        except Exception:
            pass
    # log with trace_id when available for correlation
    if result.get('trace_id'):
        logger.info("processed %s", msg_id, extra={"trace_id": result.get('trace_id'), "to": result.get('to'), "client_id": result.get('client_id')})
    else:
        logger.info("processed %s %s", msg_id, result)
    try:
        redis.incr("mgw:metrics:processed_total")
    except Exception:
        pass

    # Best-effort persistence of outbound message when conversation context is available
    try:
        with SessionLocal() as db:
            conv_id = fields.get('conversation_id')
            conv = None
            if conv_id:
                conv = db.get(DBConversation, conv_id)
            # Attempt to resolve conversation if missing and org/channel/to present
            if not conv and fields.get('org_id') and fields.get('channel_id') and fields.get('to'):
                # find contact by wa_id/phone within org
                ct = (
                    db.query(DBContact)
                    .filter(DBContact.org_id == str(fields.get('org_id')))
                    .filter((DBContact.wa_id == fields.get('to')) | (DBContact.phone == fields.get('to')))
                    .first()
                )
                if ct:
                    conv = (
                        db.query(DBConversation)
                        .filter(DBConversation.org_id == str(fields.get('org_id')))
                        .filter(DBConversation.contact_id == ct.id)
                        .filter(DBConversation.channel_id == str(fields.get('channel_id')))
                        .filter(DBConversation.state == 'open')
                        .first()
                    )
            if conv:
                # de-duplicate on client_id when available: if API already persisted an outgoing message
                # for this conversation with the same client_id, update metadata instead of inserting another row.
                existing = None
                if client_id:
                    try:
                        existing = (
                            db.query(DBMessage)
                            .filter(DBMessage.conversation_id == conv.id)
                            .filter(DBMessage.client_id == client_id)
                            .first()
                        )
                    except Exception:
                        existing = None
                if existing:
                    meta = existing.meta or {}
                    if fields.get('trace_id'):
                        meta['trace_id'] = fields.get('trace_id')
                    if result.get('wa_msg_id'):
                        meta['wa_msg_id'] = result.get('wa_msg_id')
                    existing.meta = meta if meta else None
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                else:
                    # persist new message row
                    db_msg = DBMessage(
                        id=str(uuid.uuid4()),
                        conversation_id=conv.id,
                        direction='out',
                        type=fields.get('type') or 'text',
                        content={'text': text} if text else None,
                        template_id=None,
                        status=None,
                        meta={'trace_id': fields.get('trace_id'), 'wa_msg_id': result.get('wa_msg_id')} if (fields.get('trace_id') or result.get('wa_msg_id')) else None,
                        client_id=client_id,
                    )
                    db.add(db_msg)
                    db.commit()
    except Exception:
        logger.exception("persist outbound failed")

async def loop():
    # start from the beginning in dev so backlog is processed
    last_id = "0-0"
    logger.info("send_worker starting (FAKE=%s)", FAKE)
    while True:
        try:
            # Use Redis XREAD via execute_command for consistent blocking reads
            raw = await asyncio.to_thread(redis.execute_command, 'XREAD', 'BLOCK', 5000, 'COUNT', 1, 'STREAMS', 'nf:outbox', last_id)
            if not raw:
                await asyncio.sleep(0.1)
                continue
            for stream_item in raw:
                msgs = stream_item[1]
                for msg in msgs:
                    msg_id = msg[0].decode() if isinstance(msg[0], bytes) else msg[0]
                    kvs = msg[1]
                    # redis client may return fields as a dict or a flat list of pairs
                    fields = {}
                    if isinstance(kvs, dict):
                        # values already decoded when decode_responses=True
                        for k, v in kvs.items():
                            fields[str(k)] = str(v)
                    else:
                        for i in range(0, len(kvs), 2):
                            k = kvs[i].decode() if isinstance(kvs[i], bytes) else kvs[i]
                            v = kvs[i+1].decode() if isinstance(kvs[i+1], bytes) else kvs[i+1]
                            fields[k] = v
                    last_id = msg_id
                    await process_message(msg_id, fields)
        except Exception:
            logger.exception("send_worker loop error")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(loop())
