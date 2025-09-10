# Analytics

Ubicación: `services/analytics`

Responsabilidades:
- Agregaciones y KPIs
- Endpoints de exportación

Variables de entorno:
- `DATABASE_URL`

Endpoints:
- `GET /api/analytics/kpis` — acepta `start_date` y `end_date` como query params.
- `GET /api/analytics/export` — acepta `format` (`csv`|`json`) y `limit`.

Ejecutar en dev:
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
