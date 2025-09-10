# API Reference (esbozo)

## Autenticación
- Bearer JWT para endpoints protegidos.

## Endpoints públicos (ejemplos)
- `GET /api/healthz` — estado del API Gateway.
- `POST /api/messages/send` — encolar un mensaje (payload simplificado).
- `GET /api/inbox/stream` — SSE para recibir eventos de inbox.
- `GET /internal/status` — health/status interno (servicios).

Documentación detallada por servicio en `docs/services/` (por crear).

## Auth de desarrollo (MVP)
- POST /api/auth/dev-login ? crea org/usuario y emite JWT (claims: org_id, role, sub).
- GET /api/me ? devuelve los claims del JWT actual.

Notas:
- POST /api/messages/send enriquece la carga publicada a nf:outbox con org_id y requested_by del JWT.
