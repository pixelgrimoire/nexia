# Variables de entorno

Variables principales (root `.env`)

```
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
POSTGRES_PORT
REDIS_URL
DATABASE_URL
JWT_SECRET
WHATSAPP_APP_SECRET
WHATSAPP_VERIFY_TOKEN
WHATSAPP_TOKEN
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_FAKE_MODE
TRAEFIK_HOST
```

Cada servicio puede declarar variables adicionales en su `Dockerfile` o `requirements`.
