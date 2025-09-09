# Analytics

Ubicación: `services/analytics`

Responsabilidades:
- Agregaciones y KPIs
- Endpoints de exportación

Variables de entorno:
- `DATABASE_URL`

Ejecutar en dev:
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
