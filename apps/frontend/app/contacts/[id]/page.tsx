"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Toast from "../../components/Toast";
import { getAccessToken } from "../../lib/auth";
import { type JWT, type Contact, type Channel, getContact, updateContact, deleteContact, listChannels, createChannel, createConversation } from "../../lib/api";

export default function ContactEditPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState<Contact | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [waId, setWaId] = useState("");
  const [tags, setTags] = useState<string>("");
  const [attributes, setAttributes] = useState<string>("{}");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channelId, setChannelId] = useState("");
  const [creatingConv, setCreatingConv] = useState(false);
  const [creatingChannel, setCreatingChannel] = useState(false);

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
        const c = await getContact(t, id);
        setContact(c);
        setName(c.name || "");
        setPhone(c.phone || "");
        setWaId(c.wa_id || "");
        setTags(((c.tags || []) as string[]).join(", "));
        setAttributes(JSON.stringify((c.attributes as any) || {}, null, 2));
        try {
          const chs = await listChannels(t);
          setChannels(chs);
          if (chs.length > 0) setChannelId(chs[0].id);
        } catch {}
      } catch (e: any) {
        setError(e?.message || "Error cargando contacto");
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
      let attrs: any = undefined;
      try { attrs = JSON.parse(attributes); } catch {}
      const r = await updateContact(token, id, {
        name: name.trim() || undefined,
        phone: phone.trim() || undefined,
        wa_id: waId.trim() || undefined,
        tags: tags.trim() ? tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
        attributes: attrs,
      });
      setContact(r);
      setToast({ msg: "Contacto guardado", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error guardando contacto");
      setToast({ msg: "Error guardando", type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    if (!token) return;
    if (!confirm("¿Eliminar este contacto?")) return;
    setRemoving(true);
    setError(null);
    try {
      await deleteContact(token, id);
      router.push("/contacts");
    } catch (e: any) {
      setError(e?.message || "Error eliminando contacto");
    } finally {
      setRemoving(false);
    }
  };

  const onCreateDefaultChannel = async () => {
    if (!token) return;
    setCreatingChannel(true);
    setError(null);
    try {
      const ch = await createChannel(token, {
        type: "whatsapp",
        mode: "cloud",
        status: "active",
        phone_number: "+10000000000",
        credentials: { phone_number_id: "wa_main" },
      });
      const chs = await listChannels(token);
      setChannels(chs);
      setChannelId(ch.id);
      setToast({ msg: "Canal creado", type: "success" });
    } catch (e: any) {
      setError(e?.message || "Error creando canal");
      setToast({ msg: "Error creando canal", type: "error" });
    } finally {
      setCreatingChannel(false);
    }
  };

  const onOpenConversation = async () => {
    if (!token || !channelId) return;
    setCreatingConv(true);
    setError(null);
    try {
      const conv = await createConversation(token, { contact_id: id, channel_id: channelId });
      router.push(`/conversations/${conv.id}`);
    } catch (e: any) {
      setError(e?.message || "Error abriendo conversacion");
      setToast({ msg: "Error abriendo conversacion", type: "error" });
    } finally {
      setCreatingConv(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Editar contacto</h1>
      {error && <p className="text-red-600">{error}</p>}
      {loading || !contact ? (
        <p>Cargando…</p>
      ) : (
        <div className="space-y-4">
          <section className="space-y-2">
            <h2 className="font-medium">Abrir conversacion</h2>
            <div>
              <label className="block text-sm font-medium">Canal</label>
              <select value={channelId} onChange={(e) => setChannelId(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-2 py-2">
                {channels.map((ch) => (
                  <option key={ch.id} value={ch.id}>{ch.phone_number || ch.id}</option>
                ))}
              </select>
              {channels.length === 0 && (
                <button onClick={onCreateDefaultChannel} disabled={creatingChannel} className="mt-2 px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">
                  {creatingChannel ? "Creando canal..." : "Crear canal por defecto"}
                </button>
              )}
            </div>
            <button type="button" onClick={onOpenConversation} disabled={creatingConv || !channelId} className="px-3 py-2 rounded border border-slate-300">
              {creatingConv ? "Abriendo..." : "Abrir conversacion"}
            </button>
          </section>

          <form onSubmit={onSave} className="space-y-3 max-w-lg">
          <div>
            <label className="block text-sm font-medium">Nombre</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-sm font-medium">Phone</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
            </div>
            <div>
              <label className="block text-sm font-medium">WA ID</label>
              <input value={waId} onChange={(e) => setWaId(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium">Tags (coma)</label>
            <input value={tags} onChange={(e) => setTags(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" />
          </div>
          <div>
            <label className="block text-sm font-medium">Attributes (JSON)</label>
            <textarea value={attributes} onChange={(e) => setAttributes(e.target.value)} className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 h-36 font-mono text-xs" />
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{saving ? "Guardando…" : "Guardar"}</button>
            <button type="button" onClick={onDelete} disabled={removing} className="px-3 py-2 rounded border border-red-300 text-red-700">{removing ? "Eliminando…" : "Eliminar"}</button>
          </div>
        </form>
        </div>
      )}
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}
