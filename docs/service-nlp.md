# Servicio NLP

Ubicación: `services/nlp`

Responsabilidades:
- Clasificar intención de mensajes mediante un modelo ligero (`/api/nlp/intents`).
- Extraer entidades básicas (email, teléfono, nombre) de textos (`/api/nlp/extract`).
- Servir como punto único para la capa de IA del MVP; el flow engine consume este servicio vía HTTP.

## Endpoints
- `POST /api/nlp/intents` — devuelve `primary_intent` y `top_intents` con puntajes normalizados.
- `POST /api/nlp/extract` — heurísticas regex para email/teléfono/nombre.
- `GET /healthz` — estado y versión del modelo.

## Modelado
- Pipeline `TfidfVectorizer + ComplementNB` entrenado con frases semilla en español.
- Normaliza el output a minúsculas; si el puntaje es bajo (<0.32 por defecto) retorna `default`.
- El umbral puede ajustarse via `NLP_MIN_SCORE`.

## Variables de entorno
- `NLP_MIN_SCORE`: umbral mínimo (float) para aceptar la intención primaria.
- `NLP_FALLBACK_INTENT`: etiqueta que se usa cuando no hay confianza suficiente (`default`).
- `LOG_LEVEL`: nivel de logging.

## Desarrollo
```bash
# build/run local
uvicorn app.main:app --reload --port 8004 --app-dir services/nlp/app
```

Docker: el contenedor expone `8000`, mapeado a `8004` en `docker-compose.yml`. El flow worker apunta a `http://nlp:8000` mediante la variable `NLP_SERVICE_URL`.
