# WhatsApp 24h Window Enforcement (API Gateway)

Scope
- Applies to API Gateway endpoints: `POST /api/messages/send` and `POST /api/conversations/{id}/messages`.
- Only affects `type: text` messages. Template (`type: template`) and media (`type: media`) are not blocked by the 24h rule.

Behavior
- If an inbound message exists for the conversation/contact within the last `WA_WINDOW_HOURS` (default 24h), text messages are allowed.
- If the most recent inbound is older than the window, text messages are rejected with HTTP 422 and detail: `outside-24h-window - use approved template`.
- MVP/dev exception: when no inbound history is found, text messages are allowed to avoid blocking demos. Use `WA_WINDOW_ENFORCE=false` to disable enforcement during development.

Templates
- Template sends require an approved template for the organization (matched by `name + language`).
- API Gateway validates approval before publishing to `nf:outbox`.

Metrics
- Prometheus counter (API Gateway): `nexia_api_gateway_window_blocked_total`
  - Increments on each blocked text send due to the 24h rule.
  - Exposed at `/metrics` (same-origin via frontend rewrite).

Configuration
- `WA_WINDOW_ENFORCE` (default `true`) — enable/disable enforcement.
- `WA_WINDOW_HOURS` (default `24`) — window size in hours.

Notes
- Rate limiting and idempotency are orthogonal:
  - Rate limit: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_PER_MIN` per tenant/route.
  - Idempotency: `Idempotency-Key` supported in both send endpoints; responses are cached for a short TTL.
