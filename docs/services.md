# Servicios

Listado y responsabilidades de cada servicio en `./services`.

- api-gateway: autenticação, endpoints públicos, SSE inbox.
- webhook-receiver: verificación y fan-out.
- messaging-gateway: publica/consume outbox/inbox, worker de envío.
- flow-engine: ejecuta flujos desde `nf:incoming` y encola respuestas.
- contacts: CRUD de contactos.
- analytics: endpoints de métricas.

Cada servicio tiene un `Dockerfile` y `requirements.txt` (Python) o `package.json` (frontend).
