# API Gateway

Ubicación: `services/api-gateway`

Responsabilidades:
- Auth y RBAC (por implementar)
- Endpoints públicos para mensajes y health
- SSE inbox

Archivos claves:
- `app/main.py` — contiene stubs para `POST /api/messages/send`, `/api/inbox/stream`.

Variables de entorno necesarias:
- `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`

Notas de desarrollo:
- Usar `packages/common/db.py` para conexión a DB.
- Ejecutar localmente con `uvicorn app.main:app --reload --port 8000`.
