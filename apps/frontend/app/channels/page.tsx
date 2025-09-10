"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  type JWT,
  type Channel,
  listChannels,
  createChannel,
} from "../lib/api";
import Toast from "../components/Toast";

export default function ChannelsPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);

  // form state
  const [phone, setPhone] = useState("");
  const [pnid, setPnid] = useState("");
  const [status, setStatus] = useState("active");
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("nexia_token") as JWT | null;
    setToken(t);
  }, []);

  useEffect(() => {
    if (token === null) return; // resolving
    if (!token) {
      router.push("/auth/login");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listChannels(token!);
        if (!cancelled) setChannels(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Error cargando canales");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, router]);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      await createChannel(token, {
        type: "whatsapp",
        mode: "cloud",
        status,
        phone_number: phone.trim() || undefined,
        credentials: pnid.trim() ? { phone_number_id: pnid.trim() } : undefined,
      });
      const data = await listChannels(token);
      setChannels(data);
      setPhone("");
      setPnid("");
      setToast({ msg: "Canal creado", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error creando canal");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Canales</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <section className="space-y-2">
            <h2 className="font-medium">Lista</h2>
            {channels.length === 0 && <p className="text-slate-600">No hay canales.</p>}
            <ul className="space-y-2">
              {channels.map((c) => (
                <li key={c.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                  <div className="text-sm">
                    <div className="font-mono">{c.phone_number || "(sin número)"}</div>
                    <div className="text-slate-600">pn_id: {(c.credentials as any)?.phone_number_id || "-"}</div>
                    <div className="text-slate-600">estado: {c.status || "-"}</div>
                  </div>
                  <Link className="text-blue-700 underline" href={`/channels/${c.id}`}>Editar</Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h2 className="font-medium">Nuevo canal (WA Cloud)</h2>
            <form onSubmit={onCreate} className="space-y-2">
              <div>
                <label className="block text-sm font-medium">Número (E.164)</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+5215550001111" className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
              </div>
              <div>
                <label className="block text-sm font-medium">phone_number_id</label>
                <input value={pnid} onChange={(e) => setPnid(e.target.value)} placeholder="123456789012345" className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
              </div>
              <div>
                <label className="block text-sm font-medium">Estado</label>
                <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2">
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                </select>
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
