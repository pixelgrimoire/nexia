# Flow Engine

Ubicación: `services/flow-engine`

Responsabilidades:
- Consumir `nf:incoming` (grupo de consumidores) y ejecutar flujos (nodal)
- Publicar acciones/outputs en `nf:outbox`

Variables de entorno:
- `REDIS_URL`, `DATABASE_URL`
- `FLOW_ENGINE_GROUP` (por defecto `engine`)
- `FLOW_ENGINE_CONSUMER` (por defecto hostname)
- `FLOW_ENGINE_MAX_RETRIES` (por defecto `2`)
- `FLOW_ENGINE_SCHED_POLL_MS` (por defecto `500`) — intervalo de poll del scheduler.
- `FLOW_ENGINE_SCHED_ZSET` (por defecto `nf:incoming:scheduled`) — zset de tareas diferidas.

Persistencia (MVP):
- Se crea la tabla `flow_runs` para registrar ejecuciones de flujos con campos: `id`, `org_id`, `flow_id`, `status`, `last_step`, `context`, `created_at`, `updated_at`.
- El worker persiste un registro por mensaje entrante cuando hay un Flow activo (best‑effort). Status: `completed` si emitió acciones, `running` en caso contrario.

Ejecutar en dev:
```powershell
pip install -r requirements.txt
python worker/engine_worker.py
```

Notas (MVP):
- El worker usa `XGROUP/XREADGROUP` con `ACK` para procesar `nf:incoming`.
- Reintentos automáticos hasta `FLOW_ENGINE_MAX_RETRIES`; al exceder, envía a `nf:incoming:dlq`.
- Si hay un Flow activo (`flows.status == 'active'`) para el `org_id` del evento entrante, ejecuta un subconjunto del grafo: un nodo `intent` con `map` y varios pasos `action` consecutivos del path (`send_text`, `send_template`, `send_media`). Si no hay flujo, responde con heurística simple (saludo/precio/default).
- Pasos adicionales soportados:
  - `set_attribute` (actualiza `contact.attributes[key] = value` si el contacto es localizable por `wa_id/phone`).
  - `action: "webhook"` (publica un evento `flow.webhook` en `nf:webhooks` con `data` del paso y contexto básico; el dispatcher entrega a endpoints configurados que incluyan ese tipo de evento).
  - `wait_for_reply` (pausa el flujo hasta que llegue un mensaje entrante que haga match con `pattern` opcional [regex, ignorecase]).
    - Campos: `pattern?: string`, `seconds|timeout_seconds?: number`, `timeout_path?: string`.
    - Implementación: guarda un estado de espera por `org_id/channel/contact` con TTL y token; en el próximo inbound que haga match se reanuda el path en el siguiente paso. Si vence el tiempo, el scheduler publica una reanudación hacia `timeout_path` (si está definido) o continúa con el siguiente paso.

Scheduler (wait/delay):
- Paso `wait|delay` con `seconds|sec|ms` programa una re-ejecución del flujo a partir del siguiente paso del mismo path.
- Implementación con Redis ZSET (`FLOW_ENGINE_SCHED_ZSET`) y un loop que publica a `nf:incoming` cuando vence.
- Métricas: `nexia_engine_scheduled_total`, `nexia_engine_sched_published_total`.
