"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { type JWT, type Template, getTemplate, updateTemplate, deleteTemplate } from "../../lib/api";
import { getAccessToken } from "../../lib/auth";
import Toast from "../../components/Toast";

export default function TemplateEditPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tpl, setTpl] = useState<Template | null>(null);
  // form
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [category, setCategory] = useState("utility");
  const [status, setStatus] = useState("draft");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

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
        const r = await getTemplate(t, id);
        setTpl(r);
        setName(r.name || "");
        setLanguage(r.language || "es");
        setCategory(r.category || "utility");
        setStatus(r.status || "draft");
        setBody(r.body || "");
      } catch (e: any) {
        setError(e?.message || "Error cargando plantilla");
      } finally {
        setLoading(false);
      }
    })();
  }, [id, router]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      const r = await updateTemplate(token, id, { name, language, category, status, body });
      setTpl(r);
      setToast({ msg: "Plantilla guardada", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error guardando plantilla");
      setToast({ msg: "Error guardando plantilla", type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    if (!token) return;
    if (!confirm("¿Eliminar esta plantilla?")) return;
    setRemoving(true);
    setError(null);
    try {
      await deleteTemplate(token, id);
      router.push("/templates");
    } catch (e: any) {
      setError(e?.message || "Error eliminando plantilla");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Editar plantilla</h1>
      {error && <p className="text-red-600">{error}</p>}
      {loading || !tpl ? (
        <p>Cargando…</p>
      ) : (
        <form onSubmit={onSave} className="space-y-3 max-w-lg">
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
            <label className="block text-sm font-medium">Estado</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2">
              <option value="draft">draft</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="disabled">disabled</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium">Body</label>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 h-28" />
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{saving ? "Guardando…" : "Guardar"}</button>
            <button type="button" onClick={onDelete} disabled={removing} className="px-3 py-2 rounded border border-red-300 text-red-700">{removing ? "Eliminando…" : "Eliminar"}</button>
          </div>
        </form>
      )}
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}

