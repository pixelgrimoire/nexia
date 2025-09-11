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

- Retries y DLQ (Flow Engine):
  1. El Engine usa consumer group en `nf:incoming` con reintentos automáticos (hasta `FLOW_ENGINE_MAX_RETRIES`, default 2).
  2. Al exceder el máximo, el evento se envía a `nf:incoming:dlq` con detalle `error=max-retries-exceeded`.
  3. Re-procesar: revisar `nf:incoming:dlq`, corregir causa (p. ej., payload inválido) y re-publicar a `nf:incoming` si aplica.
  4. Métricas: revisar contadores `nexia_engine_retries_total` y `nexia_engine_dlq_total` en `/metrics` del worker si `FLOW_ENGINE_METRICS=true`.

- Postgres no acepta conexiones:
  1. Comprobar `pg_isready` y crédito de volúmenes.
  2. Revisar `DATABASE_URL` en `.env`.

Añade procedimientos adicionales según evolución del proyecto.
