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
