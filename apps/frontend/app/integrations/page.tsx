"use client";
import { useEffect, useMemo, useState } from "react";
import { getAccessToken } from "../lib/auth";
import { type JWT, listOutgoingWebhooks, createOutgoingWebhook, deleteOutgoingWebhook, type OutWebhook } from "../lib/api";

export default function IntegrationsPage() {
  const [token, setToken] = useState<JWT | null>(null);
  const [rows, setRows] = useState<OutWebhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [creating, setCreating] = useState(false);
  const [events, setEvents] = useState<Array<{ id: string; type?: string | null; url?: string | null; ts?: number | null }>>([]);
  const [dlq, setDlq] = useState<Array<{ id: string; type?: string | null; url?: string | null; ts?: number | null }>>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [metrics, setMetrics] = useState<any>(null);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const load = async (t: JWT) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listOutgoingWebhooks(t);
      setRows(data);
    } catch (e: any) {
      setError(e?.message || "Error cargando integraciones");
    } finally {
      setLoading(false);
    }
  };

  const loadEvents = async (t: JWT) => {
    setLoadingEvents(true);
    try {
      const [deliv, dead] = await Promise.all([
        fetch('/api/integrations/webhooks/events?kind=delivered&limit=50').then(r => r.json()).catch(() => []),
        fetch('/api/integrations/webhooks/events?kind=dlq&limit=50').then(r => r.json()).catch(() => []),
      ]);
      setEvents(deliv as any);
      setDlq(dead as any);
      try {
        const m = await fetch('/api/integrations/metrics').then(r => r.json());
        setMetrics(m);
      } catch {}
    } finally {
      setLoadingEvents(false);
    }
  };

  useEffect(() => {
    const t = getAccessToken() as JWT | null;
    setToken(t);
    if (t) { load(t); loadEvents(t); }
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!url.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createOutgoingWebhook(token, { url: url.trim(), secret: secret.trim() || undefined });
      setUrl("");
      setSecret("");
      await load(token);
    } catch (e: any) {
      setError(e?.message || "Error creando webhook");
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!token) return;
    try {
      await deleteOutgoingWebhook(token, id);
      await load(token);
    } catch (e: any) {
      setError(e?.message || "Error eliminando webhook");
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Integraciones • Webhooks</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}

      <section className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
        <h2 className="font-medium mb-2">Nuevo endpoint</h2>
        <form onSubmit={onCreate} className="grid md:grid-cols-3 gap-3 items-end">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium">URL</label>
            <input value={url} onChange={(e) => setUrl(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" placeholder="https://acme.example.com/hooks/nexia" />
          </div>
          <div>
            <label className="block text-sm font-medium">Secret (opcional)</label>
            <input value={secret} onChange={(e) => setSecret(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <button type="submit" disabled={creating} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{creating ? 'Creando…' : 'Crear'}</button>
        </form>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Endpoints configurados</h2>
        {loading ? (
          <p>Cargando…</p>
        ) : rows.length === 0 ? (
          <p className="text-slate-600">No hay endpoints.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                <div className="text-sm">
                  <div className="font-mono">{r.url}</div>
                  <div className="text-slate-600">{(r.events || []).join(', ') || 'todos'}</div>
                </div>
                <button onClick={() => onDelete(r.id)} className="px-2 py-1 rounded border border-red-300 text-red-700 text-sm">Eliminar</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Métricas</h2>
          <button onClick={() => token && loadEvents(token)} className="px-2 py-1 rounded border border-slate-300 text-sm">Refrescar</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500">nf:outbox</div>
            <div className="text-2xl font-bold">{metrics?.messaging_gateway?.streams?.nf_outbox ?? '—'}</div>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500">nf:sent</div>
            <div className="text-2xl font-bold">{metrics?.messaging_gateway?.streams?.nf_sent ?? '—'}</div>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500">wh:delivered / dlq</div>
            <div className="text-2xl font-bold">{metrics?.webhooks?.delivered ?? '—'}<span className="text-sm text-slate-400"> / {metrics?.webhooks?.dlq ?? '—'}</span></div>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500">nf:incoming</div>
            <div className="text-2xl font-bold">{metrics?.engine?.incoming ?? '—'}</div>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500">engine scheduled</div>
            <div className="text-2xl font-bold">{metrics?.engine?.scheduled ?? '—'}</div>
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Entregas recientes</h2>
          <div className="flex items-center gap-2">
            <button onClick={() => token && loadEvents(token)} className="px-2 py-1 rounded border border-slate-300 text-sm">Refrescar</button>
            <button
              onClick={async () => {
                try { await fetch('/api/integrations/webhooks/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_type: 'webhook.test', payload: { ping: Date.now() } }) }); await loadEvents(token!); } catch {}
              }}
              className="px-2 py-1 rounded border border-emerald-300 text-emerald-700 text-sm"
            >Enviar evento de prueba</button>
          </div>
        </div>
        {loadingEvents ? (<p>Cargando…</p>) : (
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-semibold text-slate-700">Delivered</h3>
              <ul className="mt-2 space-y-1">
                {events.length === 0 ? <li className="text-sm text-slate-500">Sin eventos.</li> : events.map(ev => (
                  <li key={ev.id} className="flex items-center justify-between border border-slate-200 rounded p-2 text-sm">
                    <div className="truncate">
                      <div className="text-slate-800">{ev.type}</div>
                      <div className="text-xs text-slate-500 truncate max-w-[420px]">{ev.url}</div>
                    </div>
                    <div className="text-xs text-slate-500">{ev.ts ? new Date(ev.ts).toLocaleString() : ''}</div>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-700">DLQ</h3>
              <ul className="mt-2 space-y-1">
                {dlq.length === 0 ? <li className="text-sm text-slate-500">Sin errores.</li> : dlq.map(ev => (
                  <li key={ev.id} className="flex items-center justify-between gap-3 border border-slate-200 rounded p-2 text-sm">
                    <div className="truncate">
                      <div className="text-slate-800">{ev.type}</div>
                      <div className="text-xs text-slate-500 truncate max-w-[360px]">{ev.url || '(sin URL)'} </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="text-xs text-slate-500">{ev.ts ? new Date(ev.ts).toLocaleString() : ''}</div>
                      <button
                        className="text-xs px-2 py-1 rounded border border-amber-300 text-amber-700"
                        onClick={async () => {
                          try {
                            await fetch('/api/integrations/webhooks/retry', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: ev.id }) });
                            await loadEvents(token!);
                          } catch {}
                        }}
                      >Reintentar</button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
