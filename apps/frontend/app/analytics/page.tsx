"use client";
import { useEffect, useMemo, useState } from "react";
import { getKpis, type KpiResponse } from "../lib/api";

function StatCard({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return (
    <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
      <div className="text-3xl font-bold text-slate-800">{value}</div>
      <div className="text-sm text-slate-500">{title}</div>
      {hint && <div className="text-xs text-slate-400 mt-1">{hint}</div>}
    </div>
  );
}

type Point = { day: string; count: number };

export default function AnalyticsPage() {
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [series, setSeries] = useState<Point[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const k = await getKpis({ start_date: startDate || undefined, end_date: endDate || undefined });
      setKpis(k);
      // best-effort trend using export JSON (no extra deps)
      try {
        const q = new URLSearchParams();
        q.set("format", "json");
        q.set("limit", "500");
        const res = await fetch(`/api/analytics/export?${q.toString()}`);
        const items: Array<{ created_at: string | null }> = await res.json();
        const map = new Map<string, number>();
        for (const it of items) {
          const d = it.created_at ? it.created_at.slice(0, 10) : undefined;
          if (!d) continue;
          map.set(d, (map.get(d) || 0) + 1);
        }
        const days = Array.from(map.entries())
          .sort((a, b) => a[0].localeCompare(b[0]))
          .slice(-7)
          .map(([day, count]) => ({ day, count }));
        setSeries(days);
      } catch {}
    } catch (e: any) {
      setError(e?.message || "Error cargando analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const maxCount = useMemo(() => series.reduce((m, p) => Math.max(m, p.count), 0) || 1, [series]);

  const avgMessagesPerConversation = kpis?.avg_messages_per_conversation != null ? kpis.avg_messages_per_conversation.toFixed(1) : '--';
  const flowCompletionRate = kpis?.flow_completion_rate != null ? `${Math.round(kpis.flow_completion_rate * 100)}%` : '--';
  const flowRunsSummary = kpis?.flow_runs_total ? `${kpis.flow_runs_completed}/${kpis.flow_runs_total}` : `${kpis?.flow_runs_completed ?? 0}`;

  return (
    <main className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="text-slate-600">KPIs y tendencias basicas</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="block text-xs text-slate-600">Inicio</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-xs text-slate-600">Fin</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="border border-slate-300 rounded px-3 py-2" />
          </div>
          <button onClick={load} className="px-3 py-2 rounded bg-slate-900 text-white">Actualizar</button>
        </div>
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando...</p>
      ) : (
        <>
          {kpis && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <StatCard title="Mensajes Totales" value={kpis.total_messages} />
              <StatCard title="Mensajes Entrantes" value={kpis.inbound_messages} />
              <StatCard title="Mensajes Salientes" value={kpis.outbound_messages} />
              <StatCard title="Nuevas Conversaciones" value={kpis.new_conversations} />
              <StatCard title="Conversaciones Unicas" value={kpis.unique_conversations} />
              <StatCard title="Conversaciones Abiertas" value={kpis.open_conversations} />
              <StatCard title="Mensajes por Conversacion" value={avgMessagesPerConversation} />
              <StatCard title="Tiempo 1a Resp. (s)" value={kpis.avg_first_response_seconds != null ? Math.round(kpis.avg_first_response_seconds) : '--'} />
              <StatCard title="Tasa de respuesta" value={kpis.response_rate != null ? `${Math.round(kpis.response_rate * 100)}%` : '--'} />
              <StatCard title="Flujos Completados" value={flowRunsSummary} />
              <StatCard title="Flow Completion" value={kpis.flow_runs_total > 0 ? flowCompletionRate : '--'} />
            </div>
          )}

          {/* Trend (ultimos 7 dias, best-effort) */}
          {series.length > 0 && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
              <div className="mb-3 font-semibold text-slate-800">Tendencia (ultimos 7 dias)</div>
              <div className="grid grid-cols-7 gap-2 items-end h-40">
                {series.map((p) => (
                  <div key={p.day} className="flex flex-col items-center gap-1">
                    <div
                      className="w-full bg-slate-900 rounded"
                      style={{ height: `${Math.max(6, (p.count / maxCount) * 100)}%` }}
                      title={`${p.day}: ${p.count}`}
                    />
                    <div className="text-[10px] text-slate-500">{p.day.slice(5)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}



