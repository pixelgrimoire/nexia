# API Reference (esbozo)

## AutenticaciÃ³n
- Bearer JWT para endpoints protegidos.

## Endpoints pÃºblicos (ejemplos)
- `GET /api/healthz` â€” estado del API Gateway.
- `POST /api/messages/send` â€” encolar un mensaje (payload simplificado).
- `GET /api/inbox/stream` â€” SSE para recibir eventos de inbox.
- `GET /internal/status` â€” health/status interno (servicios).

DocumentaciÃ³n detallada por servicio en `docs/services/` (por crear).

## Auth de desarrollo (MVP)
- POST /api/auth/dev-login ? crea org/usuario y emite JWT (claims: org_id, role, sub).
- GET /api/me ? devuelve los claims del JWT actual.

Notas:
- POST /api/messages/send enriquece la carga publicada a nf:outbox con org_id y requested_by del JWT.

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

- Enviar mensaje

```http
POST /api/conversations/{id}/messages
Authorization: Bearer <JWT>
Content-Type: application/json
{
  "type": "text",
  "text": "Hola!"
}
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

Notas:
- Envíos (`POST /api/conversations/{id}/messages`) se publican en `nf:outbox` enriquecidos con `org_id`, `requested_by`, `conversation_id`, `channel_id`, `to`.
- `GET /api/inbox/stream` está protegido por roles (`admin|agent`).

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
