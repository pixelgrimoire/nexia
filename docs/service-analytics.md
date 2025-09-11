# Analytics

Ubicación: `services/analytics`

Responsabilidades:
- Agregaciones y KPIs (conteos, conversaciones únicas, tiempo promedio de primera respuesta, tasa de respuesta)
- Endpoints de exportación

Variables de entorno:
- `DATABASE_URL`

Endpoints:
- `GET /api/analytics/kpis` — acepta `start_date` y `end_date` (date) y devuelve:
  - `total_messages`, `inbound_messages`, `outbound_messages`
  - `unique_conversations`
  - `avg_first_response_seconds` (promedio desde 1er inbound a 1er outbound)
  - `response_rate` (conversaciones con respuesta / conversaciones con inbound)
- `GET /api/analytics/export` — acepta `format` (`csv`|`json`) y `limit`; exporta mensajes recientes con campos mínimos.

Ejecutar en dev:
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
