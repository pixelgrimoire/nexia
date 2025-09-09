# Runbooks y operación rápida

Problemas comunes y pasos para solución:

- Webhook receiver no responde:
  1. Verificar logs del contenedor `webhook-receiver`.
  2. Comprobar variables `WHATSAPP_APP_SECRET` y `WHATSAPP_VERIFY_TOKEN`.
  3. Probar `GET /api/webhooks/whatsapp` con token de verificación.

- Messaging gateway no envía mensajes:
  1. Verificar queue `nf:outbox` en Redis.
  2. Revisar logs del worker `messaging-gateway`.
  3. Si `WHATSAPP_FAKE_MODE=true`, mensajes no salen a Meta.

- Postgres no acepta conexiones:
  1. Comprobar `pg_isready` y crédito de volúmenes.
  2. Revisar `DATABASE_URL` en `.env`.

Añade procedimientos adicionales según evolución del proyecto.
