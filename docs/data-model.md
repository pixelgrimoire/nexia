# Modelo de datos

Resumen de las entidades principales y campos (vista lógica)

- Organization: id, name, plan, billing_status
- User: id, org_id, email, role, 2FA, status
- Channel: id, org_id, type, mode, status, credentials, phone_number
- Contact: id, org_id, wa_id, phone, name, attributes(JSONB), tags[], consent, locale, timezone
- Conversation: id, org_id, contact_id, channel_id, state, assignee, last_activity_at
- Message: id, conversation_id, direction, type, content(JSONB), template_id, status, meta, client_id
- Template: id, org_id, name, language, category, body, variables, status
- Flow: id, org_id, name, version, graph(JSON), status, created_by

Se recomienda usar Alembic/Prisma para migraciones y mantener modelos en `packages/common/models.py`. (ver `packages/common/models.py`).
