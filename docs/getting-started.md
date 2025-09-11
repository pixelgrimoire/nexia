# Getting Started

Quickstart (FAKE mode)
----------------------

Para validar el pipeline end‑to‑end rápidamente en local:

```bash
# 1) Levanta el stack (Traefik, Redis, servicios en modo FAKE). Incluye migraciones autom�ticas (servicio 'migrator').
make up

# 2) Ejecuta el smoke test E2E (simula un webhook firmado y espera un envío en nf:sent)
make smoke

# 3) (Opcional) Logs / estado
make logs   # tail de todos los servicios
make ps     # estado de contenedores
```

El smoke test pasa si nf:sent aumenta y el último evento contiene el marcador de prueba.

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

Datos de ejemplo (semilla)
--------------------------

Para probar flujos y cumplimiento de plantillas rápidamente, puedes sembrar una organización, una plantilla aprobada (`welcome`, `es`) y un flujo activo de demo:

```bash
python scripts/seed_mvp.py "Acme"
```

Esto crea:
- Organización "Acme" (si no existe)
- Plantilla `welcome` (es) con `status=approved`
- Un Flow activo con paths de ejemplo: `hola` (greeting con `wait` + `set_attribute`), `precio` (usa plantilla), y `default`.

