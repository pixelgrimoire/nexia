# API Gateway (UTF‑8)

Ubicación: `services/api-gateway`

Responsabilidades:
- Auth y RBAC vía JWT
- Endpoints públicos para mensajería y health
- SSE de inbox

Archivos clave:
- `app/main.py` — implementación de `POST /api/messages/send`, `/api/inbox/stream`, auth real (register/login/refresh/logout), conversaciones, mensajes y canales.

Variables de entorno:
- Requeridas: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`
- Opcionales:
  - `DEV_LOGIN_ENABLED` (por defecto `true`)
  - `RATE_LIMIT_ENABLED`, `RATE_LIMIT_PER_MIN`
  - `MGW_INTERNAL_URL` (URL interna del Messaging Gateway; por defecto `http://messaging-gateway:8000`)

Auth (MVP real)
- `POST /api/auth/register` → crea organización/usuario y devuelve `access_token` + `refresh_token`.
- `POST /api/auth/login` → devuelve `access_token` + `refresh_token`.
- `POST /api/auth/refresh` → rota el refresh token.
- `POST /api/auth/logout` → revoca refresh tokens del usuario o el especificado en el body.
- `GET /api/me` → devuelve los claims del access token.

Mensajería
- `POST /api/messages/send` → publica en `nf:outbox` (enriquecido con `org_id` y `requested_by`).
  - Soporta `type: text|template|media`.
  - Idempotencia: `Idempotency-Key` (TTL ~10 min). Reusa respuesta si se repite.
  - Rate limiting (opcional): `RATE_LIMIT_ENABLED`/`RATE_LIMIT_PER_MIN` por tenant/ruta.

Inbox SSE
- `GET /api/inbox/stream` → stream de eventos de `nf:inbox` (roles `admin|agent`).

Conversations/Messages
- `POST /api/conversations` → crea conversación (`state=open` por defecto).
- `GET /api/conversations` → lista por `org_id` con filtros (`state`, `include_unread`).
- `GET /api/conversations/{id}` / `PUT /api/conversations/{id}` → lectura/actualización.
- `GET /api/conversations/{id}/messages` → listados con `limit|offset|after_id`.
- `POST /api/conversations/{id}/messages` → crea mensaje saliente y publica a `nf:outbox`.
- `POST /api/conversations/{id}/messages/read` → marca inbound como `read` (opcionalmente hasta `up_to_id`).

Canales (WA Cloud / Bridge)
- `POST /api/channels` → crea un canal; requiere `phone_number` o `credentials.phone_number_id`.
- `GET /api/channels` / `GET /api/channels/{id}` / `PUT` / `DELETE` → CRUD con scoping por `org_id`.
- Unicidad dentro de la organización: `phone_number` y `credentials.phone_number_id` no se pueden repetir.
- `POST /api/channels/{id}/verify` → verifica contra Messaging Gateway y devuelve:
  - `ok`, `status`, `fake`, `has_token`, `phone_id`, `match`, `details`.

Cumplimiento (WhatsApp)
- Ventana de 24h: envío de texto fuera de 24h bloqueado (usar plantilla aprobada).
- Plantillas: los envíos `type=template` requieren plantilla `approved` en la org (match por `name + language`).

Notas de API
- Paginación: `GET /api/conversations/{id}/messages` ordena por `created_at` si existe; si no, por `id`.
- Idempotencia: cabecera `Idempotency-Key` soportada en `POST /api/messages/send` y `POST /api/conversations/{id}/messages`.
- Status interno: `GET /internal/status` expone contadores de rate limit e idempotencia.

Contactos (CRUD)
----------------

- `POST /api/contacts` — crea un contacto para la organización del token. Rechaza `org_id` distinto.
- `GET /api/contacts` — lista contactos de la organización.
- `GET /api/contacts/{id}` — obtiene un contacto de la organización.
- `PUT /api/contacts/{id}` — actualiza campos (`name`, `phone`, `wa_id`, `tags`, `attributes`, etc.).
- `DELETE /api/contacts/{id}` — elimina el contacto (requiere rol `admin`).
- `GET /api/contacts/search` — filtros in‑memory: `tags[]=...`, `attr_key`, `attr_value`.

Notas:
- Todos los endpoints requieren JWT y roles `admin|agent` (DELETE sólo `admin`).
- El scoping por `org_id` está aplicado en todas las rutas.
