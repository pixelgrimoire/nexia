"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { type JWT, type Channel, getChannel, updateChannel, deleteChannel } from "../../lib/api";

export default function ChannelEditPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [channel, setChannel] = useState<Channel | null>(null);
  // form
  const [phone, setPhone] = useState("");
  const [pnid, setPnid] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("nexia_token") as JWT | null;
    setToken(t);
    if (!t) {
      router.push("/auth/login");
      return;
    }
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const ch = await getChannel(t, id);
        setChannel(ch);
        setPhone(ch.phone_number || "");
        setPnid(((ch.credentials as any) || {}).phone_number_id || "");
        setStatus(ch.status || "active");
      } catch (e: any) {
        setError(e?.message || "Error cargando canal");
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
      const updated = await updateChannel(token, id, {
        phone_number: phone.trim() || null as any,
        status,
        credentials: pnid.trim() ? { phone_number_id: pnid.trim() } : {},
      });
      setChannel(updated);
    } catch (e: any) {
      setError(e?.message || "Error guardando canal");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    if (!token) return;
    if (!confirm("¿Eliminar este canal?")) return;
    setRemoving(true);
    setError(null);
    try {
      await deleteChannel(token, id);
      router.push("/channels");
    } catch (e: any) {
      setError(e?.message || "Error eliminando canal");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Editar canal</h1>
      {error && <p className="text-red-600">{error}</p>}
      {loading || !channel ? (
        <p>Cargando…</p>
      ) : (
        <form onSubmit={onSave} className="space-y-3 max-w-lg">
          <div>
            <label className="block text-sm font-medium">Número (E.164)</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium">phone_number_id</label>
            <input value={pnid} onChange={(e) => setPnid(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium">Estado</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{saving ? "Guardando…" : "Guardar"}</button>
            <button type="button" onClick={onDelete} disabled={removing} className="px-3 py-2 rounded border border-red-300 text-red-700">{removing ? "Eliminando…" : "Eliminar"}</button>
          </div>
        </form>
      )}
    </main>
  );
}

