"use client";
import { useEffect, useState } from "react";
import { type JWT, getMe, listConversations, type Conversation, listContacts, listFlows, type Flow, getKpis, type KpiResponse, exportAnalytics } from "../../lib/api";
import { getAccessToken } from "../../lib/auth";
import Link from "next/link";
import { ArrowRight, MessageSquare, PlusCircle, Users, Workflow } from "lucide-react";

type Status = {
  rate_limit?: { enabled?: boolean; per_min?: number; limited?: number };
  idempotency?: { reuse?: number };
};

function parsePromMetric(text: string, name: string): number | null {
  try {
    const lines = text.split(/\n+/);
    const line = lines.find((l) => l.startsWith(name + " ")) || lines.find((l) => l.startsWith(name + "{"));
    if (!line) return null;
    const parts = line.trim().split(/\s+/);
    const val = parseFloat(parts[parts.length - 1]);
    return isFinite(val) ? val : null;
  } catch {
    return null;
  }
}

function StatCard({ title, value, icon }: { title: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4">
      <div className="bg-slate-100 p-3 rounded-lg">
        {icon}
      </div>
      <div>
        <div className="text-3xl font-bold text-slate-800">{value}</div>
        <div className="text-sm text-slate-500">{title}</div>
      </div>
    </div>
  );
}

function QuickActionButton({ title, href, icon }: { title: string; href: string; icon: React.ReactNode }) {
    return (
        <Link href={href} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm hover:border-slate-300 hover:bg-slate-50 transition-all group flex flex-col justify-between">
            <div className="flex items-start justify-between">
                <div className="bg-slate-900 text-white p-2.5 rounded-lg">
                    {icon}
                </div>
                <ArrowRight className="text-slate-400 group-hover:text-slate-600 group-hover:translate-x-1 transition-transform" size={20} />
            </div>
            <div className="mt-4 text-md font-semibold text-slate-800">{title}</div>
        </Link>
    )
}


export default function DashboardPage() {
  const [user, setUser] = useState<{ email?: string; org_id?: string } | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [contactsCount, setContactsCount] = useState<number>(0);
  const [activeFlows, setActiveFlows] = useState<number>(0);
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportLimit, setExportLimit] = useState<number>(100);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);

  useEffect(() => {
    const token = getAccessToken() as JWT | null;
    if (!token) return;

    (async () => {
      try {
        setLoading(true);
        const me = await getMe(token);
        setUser(me as any);
        const convs = await listConversations(token, { limit: 5 });
        setConversations(convs);
        // Basic KPIs
        const contacts = await listContacts(token);
        setContactsCount(contacts.length);
        const flows = await listFlows(token);
        setActiveFlows(flows.filter((f: Flow) => (f as any)?.status === 'active').length);
        // Advanced KPIs (from analytics service)
        try {
          const k = await getKpis();
          setKpis(k);
        } catch {}
      } catch (e: any) {
        setError(e?.message || "Error al cargar los datos del dashboard");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const openConversations = conversations.filter(c => c.state === 'open').length;

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const onExportCsv = async () => {
    try {
      setExportingCsv(true);
      const lim = Math.min(1000, Math.max(1, exportLimit || 100));
      const { blob } = await exportAnalytics({ format: 'csv', limit: lim });
      const ts = new Date();
      const fname = `analytics-export-${ts.toISOString().replace(/[:.]/g, '-')}.csv`;
      triggerDownload(blob, fname);
    } catch (e) {
      // noop; errors visibles por consola
      console.warn(e);
    } finally {
      setExportingCsv(false);
    }
  };

  const onExportJson = async () => {
    try {
      setExportingJson(true);
      const lim = Math.min(1000, Math.max(1, exportLimit || 100));
      const { blob } = await exportAnalytics({ format: 'json', limit: lim });
      const ts = new Date();
      const fname = `analytics-export-${ts.toISOString().replace(/[:.]/g, '-')}.json`;
      triggerDownload(blob, fname);
    } catch (e) {
      console.warn(e);
    } finally {
      setExportingJson(false);
    }
  };

  return (
    <main className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Bienvenido a NexIA</h1>
        <p className="text-slate-500 mt-1">Aquí tienes un resumen de tu actividad reciente.</p>
      </div>

      {error && <p className="text-red-600 bg-red-100 p-3 rounded-lg">{error}</p>}
      
      {loading ? (
        <p>Cargando dashboard...</p>
      ) : (
        <>
          {/* --- KPIs --- */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <StatCard title="Conversaciones Abiertas" value={openConversations} icon={<MessageSquare className="text-slate-500" />} />
            <StatCard title="Contactos Totales" value={contactsCount} icon={<Users className="text-slate-500" />} />
            <StatCard title="Flujos Activos" value={activeFlows} icon={<Workflow className="text-slate-500" />} />
          </div>

          {/* --- KPIs Avanzados --- */}
          {kpis && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <StatCard
                title="Tiempo 1ª Respuesta (s)"
                value={kpis.avg_first_response_seconds != null ? Math.round(kpis.avg_first_response_seconds) : '—'}
                icon={<MessageSquare className="text-slate-500" />}
              />
              <StatCard
                title="Tasa de Respuesta"
                value={kpis.response_rate != null ? `${Math.round(kpis.response_rate * 100)}%` : '—'}
                icon={<Users className="text-slate-500" />}
              />
              <StatCard
                title="Mensajes Totales"
                value={kpis.total_messages}
                icon={<Workflow className="text-slate-500" />}
              />
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
             {/* --- Acciones Rápidas --- */}
            <div className="lg:col-span-1 space-y-6">
                 <h2 className="text-xl font-bold text-slate-800">Acciones Rápidas</h2>
                <div className="grid grid-cols-1 gap-4">
                    <QuickActionButton title="Crear un Flujo de Automatización" href="/flows/builder" icon={<Workflow size={24}/>} />
                    <QuickActionButton title="Añadir un Nuevo Contacto" href="/contacts" icon={<Users size={24}/>} />
                    <QuickActionButton title="Ver Bandeja de Entrada" href="/inbox" icon={<MessageSquare size={24}/>} />
                </div>

                {/* Export Analytics */}
                <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-3">
                  <h3 className="font-semibold text-slate-800">Exportar Analytics</h3>
                  <div>
                    <label className="block text-sm text-slate-600">Límite (1–1000)</label>
                    <input
                      type="number"
                      min={1}
                      max={1000}
                      value={exportLimit}
                      onChange={(e) => setExportLimit(parseInt(e.target.value || '0', 10))}
                      className="mt-1 w-full border border-slate-300 rounded px-3 py-2"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={onExportCsv} disabled={exportingCsv} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60 text-sm">
                      {exportingCsv ? 'Exportando…' : 'Exportar CSV'}
                    </button>
                    <button onClick={onExportJson} disabled={exportingJson} className="px-3 py-2 rounded border border-slate-300 text-sm">
                      {exportingJson ? 'Exportando…' : 'Exportar JSON'}
                    </button>
                  </div>
                </div>
            </div>

            {/* --- Conversaciones Recientes --- */}
            <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold text-slate-800">Conversaciones Recientes</h2>
                    <Link href="/conversations" className="text-sm font-semibold text-blue-600 hover:underline">Ver todas</Link>
                </div>
                <div className="space-y-3">
                    {conversations.length > 0 ? conversations.map((conv) => (
                        <Link href={`/conversations/${conv.id}`} key={conv.id} className="block p-3 rounded-lg hover:bg-slate-50 transition-colors">
                            <div className="flex justify-between items-center">
                                <div className="font-semibold text-slate-700">{conv.contact_id}</div>
                                <div className={`text-xs font-medium px-2 py-1 rounded-full ${conv.state === 'open' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>
                                    {conv.state}
                                </div>
                            </div>
                            <div className="text-sm text-slate-500 mt-1">
                                Canal: {conv.channel_id}
                            </div>
                        </Link>
                    )) : (
                        <p className="text-sm text-slate-500 text-center py-4">No hay conversaciones recientes.</p>
                    )}
                </div>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
