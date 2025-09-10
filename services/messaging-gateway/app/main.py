import os
from fastapi import FastAPI
from redis import Redis
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST


app = FastAPI(title="NexIA Messaging Gateway")

# Reutiliza la misma configuración de Redis que el worker
redis = Redis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
)

# Configuración usada por el worker para exponer su estado
FAKE = os.getenv("WHATSAPP_FAKE_MODE", "true").lower() == "true"
TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


@app.get("/internal/status")
async def status():
    """Devuelve información básica del servicio y del worker."""
    worker_info = {
        "fake": FAKE,
        "has_token": bool(TOKEN),
        "phone_id": PHONE_ID,
    }
    return {"workers": {"send_worker": worker_info}}


@app.get("/internal/metrics")
async def metrics():
    """Entrega métricas simples basadas en Redis."""
    data = {}
    try:
        data["nf_outbox"] = redis.xlen("nf:outbox")
    except Exception:
        data["nf_outbox"] = None
    try:
        data["nf_sent"] = redis.xlen("nf:sent")
    except Exception:
        data["nf_sent"] = None
    return {"streams": data}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/metrics")
async def metrics_prom():
    reg = CollectorRegistry()
    g_outbox = Gauge('nexia_mgw_nf_outbox_len', 'Length of nf:outbox stream', registry=reg)
    g_sent = Gauge('nexia_mgw_nf_sent_len', 'Length of nf:sent stream', registry=reg)
    g_fake = Gauge('nexia_mgw_fake_mode', '1 if FAKE mode enabled', registry=reg)
    g_processed = Gauge('nexia_mgw_processed_total', 'Total processed messages (from Redis)', registry=reg)
    g_errors = Gauge('nexia_mgw_errors_total', 'Total errors (from Redis)', registry=reg)
    g_wa_calls = Gauge('nexia_mgw_wa_calls_total', 'Total WhatsApp API calls (from Redis)', registry=reg)
    try:
        g_outbox.set(redis.xlen("nf:outbox"))
    except Exception:
        g_outbox.set(0)
    try:
        g_sent.set(redis.xlen("nf:sent"))
    except Exception:
        g_sent.set(0)
    g_fake.set(1 if FAKE else 0)
    try:
        g_processed.set(int(redis.get("mgw:metrics:processed_total") or 0))
        g_errors.set(int(redis.get("mgw:metrics:errors_total") or 0))
        g_wa_calls.set(int(redis.get("mgw:metrics:wa_calls_total") or 0))
    except Exception:
        pass
    data = generate_latest(reg)
    from fastapi.responses import Response
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

