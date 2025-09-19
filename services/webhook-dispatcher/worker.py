import os, json, asyncio, time, hmac, hashlib, logging
import httpx
from redis import Redis
try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

CONSUMER_GROUP = os.getenv("WH_GROUP", "wh_dispatcher")
CONSUMER_NAME = os.getenv("WH_CONSUMER", None) or os.getenv("HOSTNAME", "wh-1")
MAX_RETRIES = int(os.getenv("WH_MAX_RETRIES", "3"))

handler = logging.StreamHandler()
if jsonlogger is not None:
    handler.setFormatter(jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
else:
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
logger = logging.getLogger("webhook_dispatcher")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def _endpoints_key(org_id: str) -> str:
    return f"wh:endpoints:{org_id}"


async def _deliver(url: str, body: dict, secret: str | None):
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
        headers["X-NexIA-Signature-256"] = f"sha256={sig}"
    resp = await asyncio.to_thread(httpx.post, url, data=data, headers=headers, timeout=10)
    resp.raise_for_status()


async def process_event(fields: dict):
    org_id = fields.get("org_id") or ""
    evt_type = fields.get("type") or "event"
    body_raw = fields.get("body") or "{}"
    try:
        body = json.loads(body_raw)
    except Exception:
        body = {"raw": body_raw}
    # Load endpoints for org
    try:
        eps = redis.hgetall(_endpoints_key(org_id)) or {}
    except Exception:
        eps = {}
    if not eps:
        return
    payload = {"type": evt_type, "data": body, "org_id": org_id, "ts": int(time.time()*1000)}
    for wid, raw in eps.items():
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"url": raw}
        if obj.get("status") == "inactive":
            continue
        events = obj.get("events") or []
        if events and evt_type not in events:
            continue
        url = obj.get("url")
        secret = obj.get("secret") or None
        if not url:
            continue
        # retries
        for attempt in range(MAX_RETRIES):
            try:
                await _deliver(url, payload, secret)
                try:
                    redis.xadd("wh:delivered", {
                        "org_id": org_id,
                        "wid": wid,
                        "type": evt_type,
                        "url": url,
                        "ts": str(int(time.time()*1000)),
                    })
                except Exception:
                    pass
                break
            except Exception:
                logger.exception("webhook delivery failed (attempt %s) wid=%s", attempt+1, wid)
                if attempt < MAX_RETRIES-1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    try:
                        redis.xadd("nf:webhooks:dlq", {"org_id": org_id, "wid": wid, "type": evt_type, "body": json.dumps(body)})
                    except Exception:
                        pass


async def _ensure_group(stream: str, group: str):
    try:
        await asyncio.to_thread(redis.execute_command, 'XGROUP', 'CREATE', stream, group, '$', 'MKSTREAM')
        logger.info("created consumer group %s on %s", group, stream)
    except Exception as e:
        if "BUSYGROUP" in str(e).upper():
            return
        return


async def loop():
    stream = 'nf:webhooks'
    await _ensure_group(stream, CONSUMER_GROUP)
    logger.info("webhook dispatcher starting (group=%s consumer=%s)", CONSUMER_GROUP, CONSUMER_NAME)
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
            for stream_item in raw:
                msgs = stream_item[1]
                for msg in msgs:
                    msg_id = msg[0].decode() if isinstance(msg[0], bytes) else msg[0]
                    kvs = msg[1]
                    fields = {}
                    if isinstance(kvs, dict):
                        for k, v in kvs.items():
                            fields[str(k)] = str(v)
                    else:
                        for i in range(0, len(kvs), 2):
                            k = kvs[i].decode() if isinstance(kvs[i], bytes) else kvs[i]
                            v = kvs[i+1].decode() if isinstance(kvs[i+1], bytes) else kvs[i+1]
                            fields[k] = v
                    await process_event(fields)
                    try:
                        redis.xack(stream, CONSUMER_GROUP, msg_id)
                    except Exception:
                        logger.exception("xack failed")
        except Exception:
            logger.exception("dispatcher loop error")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(loop())
