# Arquitectura

Resumen de alto nivel y diagrama de componentes.

- Frontend: Next.js (App Router)
- API Gateway: FastAPI
- Messaging Gateway: FastAPI + worker
- Webhook Receiver: FastAPI
- Flow Engine: worker (Python)
- Contacts & Analytics: FastAPI
- NLP Service: FastAPI (intents + extracción básica)
- Infra: PostgreSQL, Redis, Traefik, MinIO (opcional)

Ver `README.md` para diagrama y modelos de datos.
