# Flow Engine

Ubicación: `services/flow-engine`

Responsabilidades:
- Consumir `nf:incoming` y ejecutar flujos (nodal)
- Publicar acciones/outputs en `nf:outbox`

Variables de entorno:
- `REDIS_URL`, `DATABASE_URL`

Ejecutar en dev:
```powershell
pip install -r requirements.txt
python worker/engine_worker.py
```
