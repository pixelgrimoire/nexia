# NexIA — Monorepo inicial (MVP dev stack)

> **Objetivo**: arrancar el entorno local con Next.js (FE) + FastAPI (BE) + Redis + Postgres + Traefik. Incluye esqueleto de servicios, colas básicas y endpoints stub para WhatsApp Cloud API.

---

## 📁 Estructura de carpetas

```
/nexia
  ├─ README.md
  ├─ docker-compose.yml
  ├─ .env.example
  ├─ .gitignore
  ├─ Makefile
  ├─ traefik/
  │   ├─ traefik.yml
  │   └─ dynamic.yml
  ├─ packages/
  │   └─ common/
  │       ├─ __init__.py
  │       ├─ db.py
  │       └─ models.py
  ├─ apps/
  │   └─ frontend/
  │       ├─ Dockerfile
  │       ├─ package.json
  │       ├─ next.config.ts
  │       ├─ tsconfig.json
  │       ├─ .env.local.example
  │       └─ app/
  │           ├─ layout.tsx
  │           ├─ page.tsx
  │           ├─ (dashboard)/dashboard/page.tsx
  │           ├─ login/page.tsx
  │           └─ lib/api.ts
  └─ services/
      ├─ api-gateway/
      │   ├─ Dockerfile
      │   ├─ requirements.txt
      │   └─ app/main.py
      ├─ webhook-receiver/
      │   ├─ Dockerfile
      │   ├─ requirements.txt
      │   └─ app/main.py
      ├─ messaging-gateway/
      │   ├─ Dockerfile
      │   ├─ requirements.txt
      │   ├─ app/main.py
      │   └─ worker/send_worker.py
      ├─ flow-engine/
      │   ├─ Dockerfile
      │   ├─ requirements.txt
      │   └─ worker/engine_worker.py
      ├─ contacts/
      │   ├─ Dockerfile
      │   ├─ requirements.txt
      │   └─ app/main.py
      └─ analytics/
          ├─ Dockerfile
          ├─ requirements.txt
          └─ app/main.py
```

---

## ⚙️ Root: docker-compose, Traefik, Makefile, README

### `.env.example`

```env
# --- Core ---
POSTGRES_USER=nf_user
POSTGRES_PASSWORD=nf_pass
POSTGRES_DB=nexia
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql+psycopg://nf_user:nf_pass@postgres:5432/nexia
JWT_SECRET=devsecret

# --- WhatsApp (simulación por defecto) ---
WHATSAPP_APP_SECRET=dev_secret
WHATSAPP_VERIFY_TOKEN=change-me
WHATSAPP_TOKEN=fake_token
WHATSAPP_PHONE_NUMBER_ID=000000000000000
WHATSAPP_FAKE_MODE=true

# --- Traefik host ---
TRAEFIK_HOST=localhost
```

### `.gitignore`

```
# Node
node_modules
.next

# Python
__pycache__
*.pyc
.venv

# Misc
.env
.env.*
.DS_Store
```

### `Makefile`

```make
up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps
```

### `traefik/traefik.yml`

```yaml
entryPoints:
  web:
    address: ":80"
api:
  dashboard: true
providers:
  file:
    filename: "/etc/traefik/dynamic.yml"
```

### `traefik/dynamic.yml`

```yaml
http:
  routers:
    frontend:
      rule: "Host(`${TRAEFIK_HOST}`) && PathPrefix(`/`)"
      service: frontend
    api_gateway:
      rule: "Host(`${TRAEFIK_HOST}`) && PathPrefix(`/api/`) && !PathPrefix(`/api/webhooks/whatsapp`)"
      service: api_gateway
    webhook_receiver:
      rule: "Host(`${TRAEFIK_HOST}`) && PathPrefix(`/api/webhooks/whatsapp`)"
      service: webhook_receiver
  services:
    frontend:
      loadBalancer:
        servers:
          - url: "http://frontend:3000"
    api_gateway:
      loadBalancer:
        servers:
          - url: "http://api-gateway:8000"
    webhook_receiver:
      loadBalancer:
        servers:
          - url: "http://webhook-receiver:8000"
```

### `docker-compose.yml`

```yaml
version: "3.9"
services:
  traefik:
    image: traefik:v3.0
    command: ["--providers.file.filename=/etc/traefik/dynamic.yml", "--api.dashboard=true", "--entrypoints.web.address=:80"]
    ports:
      - "80:80"
    volumes:
      - ./traefik/traefik.yml:/etc/traefik/traefik.yml:ro
      - ./traefik/dynamic.yml:/etc/traefik/dynamic.yml:ro
    environment:
      - TRAEFIK_HOST=${TRAEFIK_HOST}

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redisdata:/data

  frontend:
    build: ./apps/frontend
    environment:
      NEXT_PUBLIC_API_BASE: http://localhost/api
    depends_on:
      - api-gateway
    labels:
      - "traefik.enable=true"

  api-gateway:
    build: ./services/api-gateway
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      JWT_SECRET: ${JWT_SECRET}
    depends_on:
      - postgres
      - redis
    labels:
      - "traefik.enable=true"

  webhook-receiver:
    build: ./services/webhook-receiver
    environment:
      REDIS_URL: ${REDIS_URL}
      WHATSAPP_APP_SECRET: ${WHATSAPP_APP_SECRET}
      WHATSAPP_VERIFY_TOKEN: ${WHATSAPP_VERIFY_TOKEN}
    depends_on:
      - redis
    labels:
      - "traefik.enable=true"

  messaging-gateway:
    build: ./services/messaging-gateway
    environment:
      REDIS_URL: ${REDIS_URL}
      DATABASE_URL: ${DATABASE_URL}
      WHATSAPP_TOKEN: ${WHATSAPP_TOKEN}
      WHATSAPP_PHONE_NUMBER_ID: ${WHATSAPP_PHONE_NUMBER_ID}
      WHATSAPP_FAKE_MODE: ${WHATSAPP_FAKE_MODE}
    depends_on:
      - redis
      - postgres

  flow-engine:
    build: ./services/flow-engine
    environment:
      REDIS_URL: ${REDIS_URL}
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      - redis
      - postgres

  contacts:
    build: ./services/contacts
    environment:
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      - postgres

  analytics:
    build: ./services/analytics
    environment:
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      - postgres

volumes:
  pgdata:
  redisdata:
```

### `README.md`

```md
# NexIA (MVP dev stack)

## Requisitos
- Docker + Docker Compose

## Configuración
1. Copia `.env.example` a `.env` y ajusta valores.
2. `make up`
3. Abre http://localhost — Next.js FE
4. API enrutada bajo `http://localhost/api/*`
5. Webhook WhatsApp en `http://localhost/api/webhooks/whatsapp`

## Servicios clave
- **api-gateway**: `/api/healthz`, `/api/messages/send`, `/api/inbox/stream` (SSE de prueba).
- **webhook-receiver**: verifica GET + firma POST y publica eventos en Redis.
- **messaging-gateway**: consume `outbox` y simula/envía a WhatsApp.
- **flow-engine**: consume eventos entrantes y decide acciones simples.

## Flujo de prueba
- En FE, usa el botón "Simular mensaje entrante" (home) → verás en Inbox (SSE) el evento y la respuesta automática.
```

---

## 🧩 Paquete común (DB + modelos)

### `packages/common/db.py`

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://nf_user:nf_pass@postgres:5432/nexia")
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

### `packages/common/models.py`

```python
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    plan = Column(String, default="starter")
    billing_status = Column(String, default="trial")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, default="active")

class Channel(Base):
    __tablename__ = "channels"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    type = Column(String)
    mode = Column(String)
    status = Column(String)
    credentials = Column(JSONB)
    phone_number = Column(String)

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    wa_id = Column(String)
    phone = Column(String)
    name = Column(String)
    attributes = Column(JSONB, default=dict)
    tags = Column(ARRAY(String), default=list)
    consent = Column(String)
    locale = Column(String)
    timezone = Column(String)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    contact_id = Column(ForeignKey("contacts.id"))
    channel_id = Column(ForeignKey("channels.id"))
    state = Column(String)
    assignee = Column(String)
    last_activity_at = Column(DateTime)

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id"))
    direction = Column(String)  # in|out
    type = Column(String)       # text|media|template
    content = Column(JSONB)
    template_id = Column(String, nullable=True)
    status = Column(String)     # delivered|read|failed
    meta = Column(JSONB)
    client_id = Column(String)

class Template(Base):
    __tablename__ = "templates"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    language = Column(String)
    category = Column(String)
    body = Column(Text)
    variables = Column(JSONB)
    status = Column(String)

class Flow(Base):
    __tablename__ = "flows"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    version = Column(Integer)
    graph = Column(JSONB)
    status = Column(String)
    created_by = Column(String)
```

---

## 🖥️ Frontend (Next.js 15, TS)

### `apps/frontend/Dockerfile`

```dockerfile
FROM node:20-bullseye
WORKDIR /app
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./
RUN if [ -f pnpm-lock.yaml ]; then npm i -g pnpm && pnpm i; \
    elif [ -f yarn.lock ]; then yarn; \
    else npm i; fi
COPY . .
RUN npm run build || true
EXPOSE 3000
CMD ["npm","run","dev"]
```

### `apps/frontend/package.json`

```json
{
  "name": "nexia-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "15.0.1",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "reactflow": "11.10.4"
  },
  "devDependencies": {
    "typescript": "5.5.4"
  }
}
```

### `apps/frontend/next.config.ts`

```ts
import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  experimental: { appDir: true }
}
export default nextConfig
```

### `apps/frontend/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2021",
    "lib": ["ES2021", "DOM"],
    "module": "ESNext",
    "jsx": "preserve",
    "moduleResolution": "Bundler",
    "strict": true,
    "baseUrl": "."
  },
  "include": ["./**/*"]
}
```

### `apps/frontend/.env.local.example`

```env
NEXT_PUBLIC_API_BASE=http://localhost/api
```

### `apps/frontend/app/layout.tsx`

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es"><body>{children}</body></html>
  )
}
```

### `apps/frontend/app/lib/api.ts`

```ts
const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost/api";
export async function sendTestMessage(to: string) {
  const r = await fetch(`${API}/messages/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel_id: 'wa_main', to, type: 'text', text: 'Hola desde NexIA (simulado)', client_id: crypto.randomUUID() })
  });
  return r.json();
}
export function subscribeInbox(onMsg: (e: any)=>void) {
  const es = new EventSource(`${API}/inbox/stream`);
  es.onmessage = (ev) => onMsg(JSON.parse(ev.data));
  return () => es.close();
}
```

### `apps/frontend/app/page.tsx`

```tsx
'use client'
import { useEffect, useState } from 'react'
import { sendTestMessage, subscribeInbox } from './lib/api'

export default function Home() {
  const [events, setEvents] = useState<any[]>([])
  useEffect(()=>{
    const off = subscribeInbox(e => setEvents(v=>[e, ...v].slice(0,50)))
    return off
  },[])
  return (
    <main style={{padding:20}}>
      <h1>NexIA (MVP dev)</h1>
      <p>Simula un mensaje saliente y escucha eventos de Inbox (SSE).</p>
      <button onClick={()=>sendTestMessage('+5215555555555')}>Simular envío de texto</button>
      <h3>Eventos</h3>
      <pre style={{maxHeight:400, overflow:'auto', background:'#111', color:'#0f0', padding:12}}>{JSON.stringify(events, null, 2)}</pre>
    </main>
  )
}
```

### `apps/frontend/app/(dashboard)/dashboard/page.tsx`

```tsx
export default function Dashboard() {
  return <div style={{padding:20}}>Dashboard — KPIs pronto</div>
}
```

### `apps/frontend/app/login/page.tsx`

```tsx
export default function Login() {
  return <div style={{padding:20}}>Login stub (Auth.js se agrega luego)</div>
}
```

---

## 🧠 API Gateway (FastAPI)

### `services/api-gateway/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `services/api-gateway/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
redis==5.0.7
sqlalchemy==2.0.32
psycopg[binary]==3.2.10
sse-starlette==2.1.0
python-dotenv==1.0.1
```

### `services/api-gateway/app/main.py`

```python
import os, json, time
from fastapi import FastAPI, Header
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session
from packages.common.db import engine

app = FastAPI(title="NexIA API Gateway")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

class SendMessage(BaseModel):
    channel_id: str
    to: str
    type: str  # text|template
    text: str | None = None
    template: dict | None = None
    client_id: str | None = None

@app.on_event("startup")
def init_db():
    # Crea tablas mínimas si no existen
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS messages(
          id TEXT PRIMARY KEY,
          conversation_id TEXT,
          direction TEXT,
          type TEXT,
          content JSONB,
          template_id TEXT,
          status TEXT,
          meta JSONB,
          client_id TEXT
        )
        """))

@app.get("/api/healthz")
async def healthz():
    return {"ok": True, "ts": time.time()}

@app.post("/api/messages/send")
async def send_message(body: SendMessage, authorization: str | None = Header(None)):
    payload = body.dict()
    payload.setdefault("client_id", f"cli_{int(time.time()*1000)}")
    # Publica en outbox para messaging-gateway
    redis.xadd("nf:outbox", payload)
    return {"queued": True, "client_id": payload["client_id"]}

# SSE de prueba para Inbox
from sse_starlette.sse import EventSourceResponse
@app.get("/api/inbox/stream")
async def inbox_stream():
    async def event_gen():
        last_id = "$"
        while True:
            msgs = redis.xread({"nf:inbox": last_id}, block=10000, count=1)
            if msgs:
                _, entries = msgs[0]
                for msg_id, data in entries:
                    yield {"event":"message","data": json.dumps(data)}
                    last_id = msg_id
    return EventSourceResponse(event_gen())
```

Note: The repository implementation was later updated to use a FastAPI lifespan handler for startup logic and a Pydantic v1/v2-friendly pattern for payloads (using `model_dump()` when available). See `services/api-gateway/app/main.py` for the current code.

---

## 📨 Webhook Receiver (FastAPI)

### `services/webhook-receiver/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `services/webhook-receiver/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
redis==5.0.7
python-dotenv==1.0.1
```

### `services/webhook-receiver/app/main.py`

```python
import os, hmac, hashlib, json
from fastapi import FastAPI, HTTPException, Request
from redis import Redis

app = FastAPI(title="NexIA Webhook Receiver")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "change-me")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "dev_secret").encode()

@app.get("/api/webhooks/whatsapp")
async def verify(mode: str, challenge: str, verify_token: str):
    if mode == "subscribe" and verify_token == VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(403, "Forbidden")

@app.post("/api/webhooks/whatsapp")
async def receive(req: Request):
    sig = req.headers.get("X-Hub-Signature-256", "")
    body = await req.body()
    expected = "sha256=" + hmac.new(APP_SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, "Invalid signature")
    payload = await req.json()
    # Fan-out: inbox (SSE) y flujo entrante
    redis.xadd("nf:inbox", {"source":"wa","payload": json.dumps(payload)})
    redis.xadd("nf:incoming", {"source":"wa","payload": json.dumps(payload)})
    return {"ok": True}
```

---

## 📤 Messaging Gateway (FastAPI + worker)

### `services/messaging-gateway/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY worker ./worker
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `services/messaging-gateway/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
redis==5.0.7
httpx==0.27.0
python-dotenv==1.0.1
```

### `services/messaging-gateway/app/main.py`

```python
import os
from fastapi import FastAPI
from redis import Redis

app = FastAPI(title="NexIA Messaging Gateway")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

@app.get("/internal/status")
async def status():
    return {"workers": {"send_worker":"ok"}}
```

### `services/messaging-gateway/worker/send_worker.py`

```python
import os, asyncio, json
from redis import Redis
import httpx

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
FAKE = os.getenv("WHATSAPP_FAKE_MODE", "true").lower() == "true"
TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

async def send_text(to: str, text: str):
    if FAKE:
        # Solo simula
        return {"fake": True, "to": to, "text": text}
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = {"messaging_product":"whatsapp","to": to, "type":"text", "text": {"body": text}}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=data)
        r.raise_for_status()
        return r.json()

async def loop():
    last_id = "$"
    while True:
        msgs = redis.xread({"nf:outbox": last_id}, block=10000, count=1)
        if not msgs:
            continue
        _, entries = msgs[0]
        for msg_id, data in entries:
            try:
                if data.get("type") == "text":
                    res = await send_text(data.get("to",""), data.get("text",""))
                    redis.xadd("nf:inbox", {"source":"send_worker","result": json.dumps(res)})
            except Exception as e:
                redis.xadd("nf:inbox", {"source":"send_worker","error": str(e)})
            last_id = msg_id

if __name__ == "__main__":
    asyncio.run(loop())
```

> **Nota**: agrega este worker al contenedor ejecutándolo como segundo proceso (o usa `supervisord`) si deseas que corra automáticamente. En dev puedes iniciar el worker con: `docker compose exec messaging-gateway python worker/send_worker.py`.

---

## 🔁 Flow Engine (worker mínimo)

### `services/flow-engine/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker ./worker
CMD ["python", "worker/engine_worker.py"]
```

### `services/flow-engine/requirements.txt`

```
redis==5.0.7
python-dotenv==1.0.1
```

### `services/flow-engine/worker/engine_worker.py`

```python
import os, json
from redis import Redis

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

# Motor súper simple: si el texto contiene "precio" responde con una guía distinta

def classify_intent(text: str) -> str:
    t = (text or "").lower()
    if "precio" in t: return "precio"
    if "catalogo" in t or "catálogo" in t: return "catalogo"
    if "soporte" in t: return "soporte"
    return "default"

last_id = "$"
while True:
    msgs = redis.xread({"nf:incoming": last_id}, block=10000, count=1)
    if not msgs:
        continue
    _, entries = msgs[0]
    for msg_id, data in entries:
        payload = json.loads(data.get("payload","{}"))
        # Extrae texto del payload real de WhatsApp (stub en dev)
        text = payload.get("text", "hola") if isinstance(payload, dict) else "hola"
        intent = classify_intent(text)
        # Encola respuesta
        if intent == "precio":
            redis.xadd("nf:outbox", {"type":"text","to":"+5215555555555","text":"Nuestra lista de precios: ..."})
        elif intent == "catalogo":
            redis.xadd("nf:outbox", {"type":"text","to":"+5215555555555","text":"Te envío el catálogo en un momento."})
        elif intent == "soporte":
            redis.xadd("nf:outbox", {"type":"text","to":"+5215555555555","text":"Te paso con un humano de soporte."})
        else:
            redis.xadd("nf:outbox", {"type":"text","to":"+5215555555555","text":"¿En qué puedo ayudarte?"})
        last_id = msg_id
```

---

## 👥 Contacts (FastAPI stub)

### `services/contacts/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `services/contacts/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.32
psycopg[binary]==3.2.10
```

### `services/contacts/app/main.py`

```python
from fastapi import FastAPI
app = FastAPI(title="NexIA Contacts")

@app.get("/healthz")
async def healthz():
    return {"ok": True}
```

---

## 📈 Analytics (FastAPI stub)

### `services/analytics/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `services/analytics/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
```

### `services/analytics/app/main.py`

```python
from fastapi import FastAPI
app = FastAPI(title="NexIA Analytics")

@app.get("/healthz")
async def healthz():
    return {"ok": True}
```

---

## ▶️ Pasos para correr

1. Duplica `.env.example` → `.env` y ajusta `TRAEFIK_HOST=localhost`.
2. `make up` (o `docker compose up -d --build`).
3. Abre **[http://localhost](http://localhost)** → página de prueba FE.
4. Haz click en **“Simular envío de texto”** → verás eventos en el panel.
5. (Opcional) arranca el worker de envío si no lo ves activo: `docker compose exec messaging-gateway python worker/send_worker.py`.

> Cuando conectes credenciales reales de WhatsApp, desactiva `WHATSAPP_FAKE_MODE=false` y completa `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID`.

---

## ✅ Siguientes mejoras sugeridas

* Añadir Auth.js en FE y JWT en API Gateway (roles Owner/Admin/Agent/Analyst).
* Persistencia real de `messages` y `conversations` (tablas + queries).
* Editor visual con React Flow y publicación de un grafo a Redis/DB.
* Nodo **Wait** con scheduler (sorted set) y reanudación.
* Pruebas E2E (Playwright) y contract tests para payloads de Meta.
