# Webhook Receiver

Ubicación: `services/webhook-receiver`

Responsabilidades:
- Verificar token y firma de Meta
- Fan-out de eventos a Redis (`nf:inbox`, `nf:incoming`)

Variables de entorno:
- `REDIS_URL`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`

Ejecutar local (sin Docker):
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
