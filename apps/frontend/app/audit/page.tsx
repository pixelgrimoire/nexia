"use client";
import { useEffect, useMemo, useState } from "react";
import { getAccessToken } from "../lib/auth";
import { type JWT, listAudit, type AuditLog } from "../lib/api";

export default function AuditPage() {
  const [token, setToken] = useState<JWT | null>(null);
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qAction, setQAction] = useState("");
  const [qEntityType, setQEntityType] = useState("");
  const [qEntityId, setQEntityId] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    setToken(getAccessToken() as JWT | null);
  }, []);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const load = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAudit(token, {
        limit: 100,
        action: qAction.trim() || undefined,
        entity_type: qEntityType.trim() || undefined,
        entity_id: qEntityId.trim() || undefined,
      });
      setRows(data);
    } catch (e: any) {
      setError(e?.message || "Error cargando auditoría");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <main className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Auditoría</h1>
        <div className="flex items-center gap-2">
          <button onClick={load} className="px-3 py-2 rounded border border-slate-300 text-sm">Refrescar</button>
          <button
            onClick={async () => {
              if (!token) return;
              setExporting(true);
              try {
                const qs = new URLSearchParams();
                qs.set('format', 'csv');
                if (qAction.trim()) qs.set('action', qAction.trim());
                if (qEntityType.trim()) qs.set('entity_type', qEntityType.trim());
                if (qEntityId.trim()) qs.set('entity_id', qEntityId.trim());
                const res = await fetch(`/api/audit/export?${qs.toString()}`);
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `audit-export-${new Date().toISOString().replace(/[:.]/g,'-')}.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } finally {
                setExporting(false);
              }
            }}
            className="px-3 py-2 rounded border border-emerald-300 text-emerald-700 text-sm"
            disabled={exporting}
          >{exporting ? 'Exportando…' : 'Exportar CSV'}</button>
        </div>
      </div>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      <div className="grid md:grid-cols-4 gap-2 items-end">
        <div>
          <label className="block text-sm font-medium">Acción</label>
          <input value={qAction} onChange={(e) => setQAction(e.target.value)} placeholder="p.ej. message.sent" className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium">Tipo</label>
          <input value={qEntityType} onChange={(e) => setQEntityType(e.target.value)} placeholder="flow|template|channel|..." className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium">Entidad ID</label>
          <input value={qEntityId} onChange={(e) => setQEntityId(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
        </div>
        <button onClick={load} className="px-3 py-2 rounded bg-slate-900 text-white">Buscar</button>
      </div>
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-slate-600">
                <th className="py-2 pr-4">Fecha</th>
                <th className="py-2 pr-4">Actor</th>
                <th className="py-2 pr-4">Acción</th>
                <th className="py-2 pr-4">Tipo</th>
                <th className="py-2 pr-4">Entidad</th>
                <th className="py-2 pr-4">Datos</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-200">
                  <td className="py-2 pr-4 whitespace-nowrap">{r.created_at ? new Date((r.created_at as number) * 1000).toLocaleString() : ''}</td>
                  <td className="py-2 pr-4">{r.actor || '—'}</td>
                  <td className="py-2 pr-4">{r.action}</td>
                  <td className="py-2 pr-4">{r.entity_type || '—'}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.entity_id || '—'}</td>
                  <td className="py-2 pr-4 text-xs text-slate-600 max-w-[36rem] break-words">{r.data ? JSON.stringify(r.data) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
