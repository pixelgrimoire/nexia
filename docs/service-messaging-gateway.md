# Messaging Gateway

Ubicación: `services/messaging-gateway`

Responsabilidades:
- Exponer endpoints internos de estado y métricas (`GET /internal/status`, `GET /internal/metrics`)
- Worker `send_worker.py` que consume `nf:outbox` y envía a la API de WhatsApp (o simula si FAKE)

Variables de entorno:
- `REDIS_URL`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_FAKE_MODE`

Endpoints internos:
- `GET /internal/status` — muestra modo del `send_worker` y datos básicos de Redis.
- `GET /internal/metrics` — entrega contadores de los streams `nf:outbox` y `nf:sent`.

Ejecutar worker en dev:
```powershell
docker compose exec messaging-gateway python worker/send_worker.py
```
