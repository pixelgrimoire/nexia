# NexIA — Monorepo inicial (MVP dev stack)

> Objetivo: arrancar el entorno local con Next.js (FE) + FastAPI (BE) + Redis + Postgres + Traefik. Incluye servicios, colas y endpoints (WhatsApp Cloud en modo FAKE por defecto).

## Quickstart (FAKE mode)

```bash
# Levantar stack
make up

# Smoke test E2E (simula webhook y verifica nf:sent)
make smoke

# Logs / estado
make logs
make ps
```

Revisa `docs/getting-started.md` para más detalles y troubleshooting.

---

## Estructura de carpetas (resumen)

```
/nexia
  ├── docker-compose.yml
  ├── Makefile
  ├── traefik/
  ├── packages/common/
  ├── apps/frontend/
  └── services/
      ├── api-gateway/
      ├── webhook-receiver/
      ├── messaging-gateway/
      ├── flow-engine/
      ├── contacts/
      └── analytics/
```

## Comandos útiles

```bash
make up       # docker compose up -d --build
make down     # docker compose down -v
make logs     # logs -f --tail=200
make ps       # estado de contenedores
make smoke    # prueba E2E (webhook -> engine -> outbox -> sent)
```

## Notas
- Modo FAKE evita llamadas externas a WhatsApp; ideal para desarrollo.
- Cambia variables en `.env` según `docs/env-vars.md`.
- Métricas Prometheus disponibles en los servicios: consulta `/metrics` cuando aplique.
