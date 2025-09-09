# API Reference (esbozo)

## Autenticación
- Bearer JWT para endpoints protegidos.

## Endpoints públicos (ejemplos)
- `GET /api/healthz` — estado del API Gateway.
- `POST /api/messages/send` — encolar un mensaje (payload simplificado).
- `GET /api/inbox/stream` — SSE para recibir eventos de inbox.
- `GET /internal/status` — health/status interno (servicios).

Documentación detallada por servicio en `docs/services/` (por crear).
