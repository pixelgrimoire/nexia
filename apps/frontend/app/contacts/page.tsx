"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Toast from "../components/Toast";
import { getAccessToken } from "../lib/auth";
import { type JWT, type Contact, listContacts, searchContacts, createContact } from "../lib/api";

export default function ContactsPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Contact[]>([]);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  // filters
  const [tagsQ, setTagsQ] = useState("");
  const [attrKey, setAttrKey] = useState("");
  const [attrVal, setAttrVal] = useState("");

  // create form
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [waId, setWaId] = useState("");
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
        const data = await listContacts(t);
        setRows(data);
      } catch (e: any) {
        setError(e?.message || "Error cargando contactos");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setLoading(true);
    try {
      const tags = tagsQ.trim() ? tagsQ.split(",").map((t) => t.trim()).filter(Boolean) : [];
      const data = await searchContacts(token, { tags, attr_key: attrKey.trim() || undefined, attr_value: attrVal.trim() || undefined });
      setRows(data);
    } catch (e: any) {
      setError(e?.message || "Error buscando");
    } finally {
      setLoading(false);
    }
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!phone.trim() && !waId.trim()) {
      setToast({ msg: "Ingresa phone o wa_id", type: "error" });
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createContact(token, { name: name.trim() || undefined, phone: phone.trim() || undefined, wa_id: waId.trim() || undefined });
      const data = await listContacts(token);
      setRows(data);
      setName(""); setPhone(""); setWaId("");
      setToast({ msg: "Contacto creado", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error creando contacto");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Contactos</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      <section className="space-y-2">
        <h2 className="font-medium">Buscar</h2>
        <form onSubmit={onSearch} className="grid md:grid-cols-4 gap-2 items-end">
          <div>
            <label className="block text-sm font-medium">Tags (coma)</label>
            <input value={tagsQ} onChange={(e) => setTagsQ(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium">Attr key</label>
            <input value={attrKey} onChange={(e) => setAttrKey(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium">Attr value</label>
            <input value={attrVal} onChange={(e) => setAttrVal(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <button type="submit" className="px-3 py-2 rounded bg-slate-900 text-white">Buscar</button>
        </form>
      </section>
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <section className="space-y-2">
            <h2 className="font-medium">Lista</h2>
            {rows.length === 0 && <p className="text-slate-600">No hay contactos.</p>}
            <ul className="space-y-2">
              {rows.map((c) => (
                <li key={c.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                  <div className="text-sm">
                    <div className="font-mono">{c.name || c.phone || c.wa_id || c.id}</div>
                    <div className="text-slate-600">{c.phone || "-"} · {c.wa_id || "-"}</div>
                  </div>
                  <Link href={`/contacts/${c.id}`} className="text-blue-700 underline">Editar</Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h2 className="font-medium">Nuevo contacto</h2>
            <form onSubmit={onCreate} className="space-y-2">
              <div>
                <label className="block text-sm font-medium">Nombre</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium">Phone</label>
                  <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+521..." className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
                </div>
                <div>
                  <label className="block text-sm font-medium">WA ID</label>
                  <input value={waId} onChange={(e) => setWaId(e.target.value)} placeholder="wa_id" className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
                </div>
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

