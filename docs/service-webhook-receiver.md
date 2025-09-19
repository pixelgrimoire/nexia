# Webhook Receiver

Ubicación: `services/webhook-receiver`

Responsabilidades:
- Verificar token y firma de Meta
- Fan-out de eventos a Redis (`nf:inbox`, `nf:incoming`)
- Enriquecimiento multi-tenant: resuelve `org_id` y `channel_id` a partir de `metadata.phone_number_id` (o `display_phone_number`) consultando la tabla `channels`.
- Actualiza estados de mensajes salientes a partir de `statuses[]` del webhook (sent/delivered/read/failed) haciendo match por `wa_msg_id` y emite evento `message.status` en `nf:webhooks`.

Variables de entorno:
- `REDIS_URL`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`
  (usa `DATABASE_URL` del proyecto para buscar `channels`)

Ejecutar local (sin Docker):
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
