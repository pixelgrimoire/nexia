# Getting Started

Requisitos:
- Docker y Docker Compose
- Node.js (para desarrollo frontend opcional)
- Python 3.12 (para ejecutar servicios localmente sin Docker)

Pasos rápidos (PowerShell):

1. Copia el archivo de ejemplo y ajusta variables si es necesario:

```powershell
Copy-Item .env.example .env
```

2. Levanta el stack (recomendado):

```powershell
docker compose up -d --build
```

3. Comprueba que los contenedores corren:

```powershell
docker compose ps
```

4. Ver logs en tiempo real (útil para debugging):

```powershell
docker compose logs -f --tail 200
```

Prueba rápida (flujo webhook -> engine -> outbox -> send worker):

1. Envía un POST simulado al webhook receiver (reemplaza host si usas Traefik):

```powershell
$body = @{
	entry = @(@{ changes = @(@{ value = @{ messages = @(@{ text = @{ body = 'Hola, quiero saber el precio' } }) } }) })
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri http://localhost:8000/api/webhooks/whatsapp -Method Post -Body $body -ContentType 'application/json' -Headers @{ 'X-Hub-Signature-256' = 'sha256=fake-signature-for-dev' }
```

Nota: en desarrollo `WHATSAPP_FAKE_MODE=true` evita llamadas externas; el webhook receptor añadirá el evento a `nf:incoming` y a `nf:inbox`.

2. Verifica que `flow-worker` generó una respuesta en `nf:outbox` y que `messaging-worker` procesó la cola. Puedes inspeccionar Redis dentro del contenedor:

```powershell
docker compose exec redis redis-cli --raw XREVRANGE nf:outbox + - COUNT 10
docker compose exec redis redis-cli --raw XREVRANGE nf:sent + - COUNT 10
```

3. Abrir la SSE del inbox (en navegador):

```
http://localhost:8000/api/inbox/stream
```

Comandos útiles:

```powershell
# Levantar todo
make up
# Ver logs
make logs
# Parar y eliminar volúmenes
make down
```

Troubleshooting rápido:
- Si los workers no aparecen en logs, comprueba `docker compose ps` y el log del servicio `messaging-worker` / `flow-worker`.
- Si Redis no está disponible, los endpoints REST aún responderán pero las colas no se procesarán.
- Para pruebas locales sin Docker, exporta `REDIS_URL` y ejecuta los workers con Python:

```powershell
$env:REDIS_URL = 'redis://localhost:6379/0'; python services\flow-engine\worker\engine_worker.py
```

Ejemplos de payloads y pruebas adicionales están en `docs/`.
