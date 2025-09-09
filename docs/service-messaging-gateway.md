# Messaging Gateway

Ubicación: `services/messaging-gateway`

Responsabilidades:
- Exponer endpoints internos de estado
- Worker `send_worker.py` que consume `nf:outbox` y envía a la API de WhatsApp (o simula si FAKE)

Variables de entorno:
- `REDIS_URL`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_FAKE_MODE`

Ejecutar worker en dev:
```powershell
docker compose exec messaging-gateway python worker/send_worker.py
```
