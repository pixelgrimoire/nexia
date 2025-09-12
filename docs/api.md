# API Reference (esbozo)

## Autenticación
- Bearer JWT para endpoints protegidos.

### Auth real (MVP)

Registro (crea organización + usuario):

```bash
curl -X POST http://$HOST/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"Secret123","org_name":"Acme"}'
```

Login:

```bash
curl -X POST http://$HOST/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"Secret123"}'
```

Refresh:

```bash
curl -X POST http://$HOST/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<token>"}'
```

Logout (revoca refresh del usuario actual):

```bash
curl -X POST http://$HOST/api/auth/logout \
  -H "Authorization: Bearer $ACCESS" -d '{}'
```

## Endpoints públicos (ejemplos)
- `GET /api/healthz` — estado del API Gateway.
- `POST /api/messages/send` — encolar un mensaje (text/template/media).
- `GET /api/inbox/stream` — SSE para recibir eventos de inbox.
- `GET /internal/status` — health/status interno (servicios).

## Conversations/Messages (MVP)

- Crear conversación

```http
POST /api/conversations
Authorization: Bearer <JWT>
Content-Type: application/json
{
  "contact_id": "ct_123",
  "channel_id": "wa_main",
  "assignee": "u1"
}
```

- Listar mensajes (paginación y cursor)

```http
GET /api/conversations/{id}/messages?limit=50&offset=0&after_id=m_20
Authorization: Bearer <JWT>
```

- Enviar mensaje (texto)

```http
POST /api/conversations/{id}/messages
Authorization: Bearer <JWT>
Content-Type: application/json
{
  "type": "text",
  "text": "Hola!"
}
```

- Enviar plantilla (template)

```bash
curl -X POST http://$HOST/api/messages/send \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{
    "channel_id":"wa_main",
    "to":"5215550001111",
    "type":"template",
    "template": {"name":"welcome","language":{"code":"es"},"components":[]}
  }'
```

- Enviar media

```bash
curl -X POST http://$HOST/api/messages/send \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{
    "channel_id":"wa_main",
    "to":"5215550001111",
    "type":"media",
    "media": {"kind":"image","link":"https://example.com/demo.jpg","caption":"Hola"}
  }'
```

- Marcar como leídos

```http
POST /api/conversations/{id}/messages/read
Authorization: Bearer <JWT>
Content-Type: application/json
{
  "up_to_id": "m_42"
}
```

## Channels (WA Cloud / Bridge)

- Crear canal (WA Cloud)

```http
POST /api/channels
Authorization: Bearer <JWT (admin)>
Content-Type: application/json
{
  "type": "whatsapp",
  "mode": "cloud",
  "phone_number": "+5215550001111",
  "credentials": {"phone_number_id": "123456789012345"}
}
```

- Listar/editar/borrar

```http
GET /api/channels
GET /api/channels/{id}
PUT /api/channels/{id}
DELETE /api/channels/{id}
```

- Verificar canal (ping a Messaging Gateway)

```http
POST /api/channels/{id}/verify
Authorization: Bearer <JWT>
```

Respuesta:

```json
{
  "ok": true,
  "status": "ok",
  "fake": true,
  "has_token": false,
  "phone_id": "111",
  "match": true,
  "details": "fake-mode"
}
```

Notas:
- Envíos (`POST /api/conversations/{id}/messages`) se publican en `nf:outbox` enriquecidos con `org_id`, `requested_by`, `conversation_id`, `channel_id`, `to`.
- `GET /api/inbox/stream` está protegido por roles (`admin|agent`).

## Flows (CRUD básico)

- Listar flujos

```http
GET /api/flows
Authorization: Bearer <JWT>
```

- Crear flujo

```http
POST /api/flows
Authorization: Bearer <JWT (admin)>
Content-Type: application/json
{
  "name": "Lead Qualifier",
  "version": 1,
  "graph": {"nodes": [], "paths": {}},
  "status": "draft"
}
```

- Actualizar flujo (publicar activa y desactiva el resto)

```http
PUT /api/flows/{id}
Authorization: Bearer <JWT (admin)>
Content-Type: application/json
{
  "status": "active"
}
```

- Eliminar flujo

## Contacts (CRUD)

- Crear contacto

```http
POST /api/contacts
Authorization: Bearer <JWT>
Content-Type: application/json
{
  "name": "Ana",
  "phone": "+5215550001111",
  "wa_id": "5215550001111",
  "tags": ["lead"],
  "attributes": {"source": "web"}
}
```

- Listar/obtener/actualizar/borrar

```http
GET /api/contacts
GET /api/contacts/{id}
PUT /api/contacts/{id}
DELETE /api/contacts/{id}
```

- Buscar (in-memory):

```http
GET /api/contacts/search?tags=vip&tags=lead&attr_key=source&attr_value=web
Authorization: Bearer <JWT>
```

```http
DELETE /api/flows/{id}
Authorization: Bearer <JWT (admin)>
```

## SSE Inbox

- cURL:

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Accept: text/event-stream" http://$HOST/api/inbox/stream
```

- Fetch (browser/Next.js):

```ts
import { subscribeInbox } from "@/app/lib/api";

const stop = subscribeInbox(token, (data) => {
  // data is the raw SSE data payload (string)
  console.log("inbox event:", data);
});

// later: stop();
```

## Idempotency-Key

- En envíos (`POST /api/messages/send`) y en mensajes de conversación (`POST /api/conversations/{id}/messages`) puedes enviar la cabecera:

```
Idempotency-Key: 7b0f6b1a-2a8a-4b1a-9f2e-123456789abc
```

Si se repite la misma clave para el mismo tenant y ruta, el Gateway devuelve 200 con el mismo body previo y no re‑publica a la cola ni duplica efectos. Cache TTL aproximado: 10 minutos.

## Rate limiting

- Por tenant y ruta, ventana fija por minuto. Variables:
  - `RATE_LIMIT_ENABLED` (on/off)
  - `RATE_LIMIT_PER_MIN` (por defecto 60)

## Status interno

- `GET /internal/status` muestra métricas simples:
  - `rate_limit.limited`: cantidad de peticiones limitadas
  - `idempotency.reuse`: cantidad de reusos de idempotencia
