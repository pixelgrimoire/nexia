# API Gateway

Ubicación: `services/api-gateway`

Responsabilidades:
- Auth y RBAC via JWT
- Endpoints públicos para mensajes y health
- SSE inbox

Archivos claves:
- `app/main.py` — contiene stubs para `POST /api/messages/send`, `/api/inbox/stream`.

Variables de entorno necesarias:
- `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`

Notas de desarrollo:
- Usar `packages/common/db.py` para conexión a DB.
- Ejecutar localmente con `uvicorn app.main:app --reload --port 8000`.
- Middleware `jwt_middleware` valida el header `Authorization` con `JWT_SECRET` y adjunta el payload al request.
- Decorador `require_roles` (roles: `admin`, `agent`) protege rutas:

```python
@app.post("/api/messages/send")
async def send_message(body: SendMessage, user: dict = require_roles(Role.admin, Role.agent)):
    ...
```

Actualizaciones (MVP dev)
- SSE `/api/inbox/stream` está protegido por roles (`admin`|`agent`).
- `POST /api/messages/send` añade `org_id` y `requested_by` a la carga publicada en `nf:outbox` (enriquecimiento multi-tenant).
- Endpoints de desarrollo:
  - `POST /api/auth/dev-login` → emite JWT y crea org/usuario si no existen.
  - `GET /api/me` → devuelve los claims del token.

Variables adicionales:
- `DEV_LOGIN_ENABLED` (por defecto `true` en dev) para habilitar/ocultar `/api/auth/dev-login`.
- `RATE_LIMIT_ENABLED` y `RATE_LIMIT_PER_MIN` (límite fijo por minuto por `org_id` y ruta; implementación en memoria para dev; usar Redis en el futuro para instancias múltiples).

Conversations/Messages (MVP)
- `POST /api/conversations` crea una conversación (state por defecto `open`).
- `GET /api/conversations` lista conversaciones por `org_id` con filtro opcional `state`.
- `GET /api/conversations/{id}` y `PUT /api/conversations/{id}` lectura/actualización con scoping.
- `GET /api/conversations/{id}/messages` lista mensajes.
- `POST /api/conversations/{id}/messages` crea mensaje saliente y publica en `nf:outbox` (`org_id`, `requested_by`, `conversation_id`, `channel_id`, `to`).


Channels (WA Cloud / Bridge)
- POST /api/channels crea un canal para la org del token. Requiere phone_number o credentials.phone_number_id.
- GET /api/channels lista canales de la org.
- GET /api/channels/{id}, PUT, DELETE con scoping por org_id.
- Unicidad por org_id: phone_number y credentials.phone_number_id no pueden repetirse dentro de la misma organizaci�n.

