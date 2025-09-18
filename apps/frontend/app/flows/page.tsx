"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Toast from "../components/Toast";
import { getAccessToken } from "../lib/auth";
import { type JWT, listFlows, createFlow, updateFlow, deleteFlow, type Flow } from "../lib/api";

const DEFAULT_GRAPH = {
  name: "Demo",
  nodes: [
    { id: "t1", type: "trigger", on: "message_in" },
    { id: "i1", type: "intent", map: { greeting: "path_hola", default: "path_default" } },
  ],
  paths: {
    path_hola: [ { type: "action", action: "send_text", text: "Hola!" } ],
    path_default: [ { type: "action", action: "send_text", text: "Gracias" } ],
  },
};

export default function FlowsPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [rows, setRows] = useState<Flow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  // form
  const [name, setName] = useState("Nuevo flujo");
  const [version, setVersion] = useState<number>(1);
  const [graphText, setGraphText] = useState(JSON.stringify(DEFAULT_GRAPH, null, 2));
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const t = getAccessToken() as JWT | null;
    setToken(t);
    if (!t) {
      router.push("/auth/login");
      return;
    }
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listFlows(t);
        setRows(data);
      } catch (e: any) {
        setError(e?.message || "Error cargando flujos");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const refresh = async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(await listFlows(token));
    } catch {}
    setLoading(false);
  };

  const onCreateDemo = async () => {
    if (!token) return;
    setError(null);
    try {
      const demo = {
        name: "Wait Reply Demo",
        version: 1,
        status: "active",
        graph: {
          name: "Wait Reply Demo",
          nodes: [
            { id: "i1", type: "intent", map: { greeting: "path_welcome", default: "path_welcome" } },
          ],
          paths: {
            path_welcome: [
              { type: "action", action: "send_text", text: "Hola! Envíame un código de 6 dígitos." },
              { type: "wait_for_reply", pattern: "\\\\d{6}", seconds: 30, timeout_path: "path_timeout" },
              { type: "action", action: "send_text", text: "¡Código recibido! Gracias." },
              { type: "action", action: "webhook", data: { event: "code_received" } },
            ],
            path_timeout: [
              { type: "action", action: "send_text", text: "No recibí tu código. ¿Podemos intentar de nuevo?" },
            ],
          },
        },
      } as any;
      await createFlow(token, demo);
      await refresh();
      setToast({ msg: "Flujo demo creado y activado", type: "success" });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error creando flujo demo", type: "error" });
    }
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      let graph: any = undefined;
      try { graph = JSON.parse(graphText); } catch {}
      await createFlow(token, { name: name.trim(), version, graph });
      await refresh();
      setToast({ msg: "Flujo creado", type: "success" });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error creando flujo", type: "error" });
      setError(e?.message || "Error creando");
    } finally {
      setCreating(false);
    }
  };

  const onActivate = async (id: string) => {
    if (!token) return;
    try {
      await updateFlow(token, id, { status: "active" });
      await refresh();
      setToast({ msg: "Flujo activado", type: "success" });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error activando flujo", type: "error" });
    }
  };

  const onDelete = async (id: string) => {
    if (!token) return;
    if (!confirm("¿Eliminar este flujo?")) return;
    try {
      await deleteFlow(token, id);
      await refresh();
      setToast({ msg: "Flujo eliminado", type: "success" });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error eliminando flujo", type: "error" });
    }
  };

  return (
    <main className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Flujos</h1>
        <div className="flex items-center gap-2">
          <button onClick={onCreateDemo} className="text-sm px-3 py-1.5 rounded border border-emerald-300 text-emerald-700 hover:bg-emerald-50">Crear Flujo Demo</button>
          <a href="/flows/builder" className="text-sm px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50">Abrir Builder</a>
        </div>
      </div>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <section className="space-y-2">
            <h2 className="font-medium">Lista</h2>
            {rows.length === 0 && <p className="text-slate-600">No hay flujos.</p>}
            <ul className="space-y-2">
              {rows.map((f) => (
                <li key={f.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                  <div className="text-sm">
                    <div className="font-mono">{f.name} v{f.version}</div>
                    <div className="text-slate-600">{f.status || "-"}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => onActivate(f.id)} className="px-2 py-1 rounded border border-slate-300 text-sm">Activar</button>
                    <button onClick={() => onDelete(f.id)} className="px-2 py-1 rounded border border-red-300 text-red-700 text-sm">Eliminar</button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h2 className="font-medium">Nuevo flujo</h2>
            <form onSubmit={onCreate} className="space-y-2">
              <div>
                <label className="block text-sm font-medium">Nombre</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
              </div>
              <div>
                <label className="block text-sm font-medium">Versión</label>
                <input type="number" value={version} onChange={(e) => setVersion(Number(e.target.value) || 1)} className="mt-1 block w-32 border border-slate-300 rounded px-3 py-2" />
              </div>
              <div>
                <label className="block text-sm font-medium">Grafo (JSON)</label>
                <textarea value={graphText} onChange={(e) => setGraphText(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 h-40 font-mono text-xs" />
              </div>
              <button type="submit" disabled={creating} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{creating ? "Creando…" : "Crear"}</button>
            </form>
          </section>
        </div>
      )}
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}
