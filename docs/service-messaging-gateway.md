# Messaging Gateway

Ubicación: `services/messaging-gateway`

Responsabilidades:
- Exponer endpoints internos de estado y métricas (`GET /internal/status`, `GET /internal/metrics`, `GET /metrics`)
- Worker `send_worker.py` que consume `nf:outbox` y envía a la API de WhatsApp (o simula si FAKE)

Variables de entorno:
- `REDIS_URL`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_FAKE_MODE`

Tipos de mensajes soportados
- `text`: `{ type: "text", text: { body } }`
- `template`: `{ type: "template", template: { name, language, components? } }`
- `media` (image|document|video|audio): `{ type: kind, [kind]: { link, caption? } }`

Ejemplos (payload producido hacia Meta)

```json
{
  "messaging_product": "whatsapp",
  "to": "+5215550001111",
  "type": "template",
  "template": { "name": "welcome", "language": { "code": "es" } }
}
```

```json
{
  "messaging_product": "whatsapp",
  "to": "+5215550001111",
  "type": "image",
  "image": { "link": "https://example.com/demo.jpg", "caption": "Hola" }
}
```

Notas
- Modo FAKE: no llama a Meta; refleja campos clave en `nf:sent` (e.g., `template_name`, `media_kind`).
- Ventana de 24h: fuera de la ventana se requieren plantillas aprobadas; manejar errores de Meta en logs y métricas.
- Métricas Prometheus en `/metrics` y JSON en `/internal/metrics`.
