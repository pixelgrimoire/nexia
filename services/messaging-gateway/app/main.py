import os
from fastapi import FastAPI
from redis import Redis


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

