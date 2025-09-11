"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { type JWT, type Template, listTemplates, createTemplate } from "../lib/api";
import { getAccessToken } from "../lib/auth";
import Toast from "../components/Toast";

export default function TemplatesPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Template[]>([]);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);
  // form
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [category, setCategory] = useState("utility");
  const [body, setBody] = useState("");
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
        const data = await listTemplates(t);
        setRows(data);
      } catch (e: any) {
        setError(e?.message || "Error cargando plantillas");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      await createTemplate(token, { name: name.trim(), language, category, body: body.trim() || undefined });
      const data = await listTemplates(token);
      setRows(data);
      setName("");
      setBody("");
      setToast({ msg: "Plantilla creada", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error creando plantilla");
      setToast({ msg: "Error creando plantilla", type: "error" });
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Plantillas</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <section className="space-y-2">
            <h2 className="font-medium">Lista</h2>
            {rows.length === 0 && <p className="text-slate-600">No hay plantillas.</p>}
            <ul className="space-y-2">
              {rows.map((t) => (
                <li key={t.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                  <div className="text-sm">
                    <div className="font-mono">{t.name} ({t.language})</div>
                    <div className="text-slate-600">{t.category || "-"} · {t.status || "-"}</div>
                  </div>
                  <Link className="text-blue-700 underline" href={`/templates/${t.id}`}>Editar</Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h2 className="font-medium">Nueva plantilla</h2>
            <form onSubmit={onCreate} className="space-y-2">
              <div>
                <label className="block text-sm font-medium">Nombre</label>
                <input value={name} onChange={(e) => setName(e.target.value)} required className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium">Idioma</label>
                  <input value={language} onChange={(e) => setLanguage(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
                </div>
                <div>
                  <label className="block text-sm font-medium">Categoría</label>
                  <select value={category} onChange={(e) => setCategory(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2">
                    <option value="utility">utility</option>
                    <option value="marketing">marketing</option>
                    <option value="authentication">authentication</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium">Body</label>
                <textarea value={body} onChange={(e) => setBody(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 h-28" />
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

