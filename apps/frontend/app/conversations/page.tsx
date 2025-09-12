"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type JWT,
  listConversations,
  listChannels,
  listContacts,
  createConversation,
  createChannel,
  type Conversation,
  type Channel,
  type Contact,
} from "../lib/api";
import { getAccessToken } from "../lib/auth";

export default function ConversationsPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);

  // form state
  const [contactId, setContactId] = useState("");
  const [contactQuery, setContactQuery] = useState("");
  const [channelId, setChannelId] = useState("");
  const [creating, setCreating] = useState(false);
  const [creatingChannel, setCreatingChannel] = useState(false);

  useEffect(() => {
    const t = getAccessToken();
    setToken(t as JWT | null);
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [cList, chList, ctList] = await Promise.all([
          listConversations(token, { limit: 50, include_unread: true }),
          listChannels(token),
          listContacts(token),
        ]);
        if (!cancelled) {
          setConvs(cList);
          setChannels(chList);
          setContacts(ctList);
          if (chList.length > 0) setChannelId(chList[0].id);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Error cargando datos");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const hasToken = useMemo(() => Boolean(token), [token]);

  useEffect(() => {
    if (token === null) return; // resolving
    if (!token) router.push("/auth/login");
  }, [token, router]);

  const onCreateConv = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      const contactValue = (contactId || contactQuery).trim();
      if (!contactValue) throw new Error("Contacto requerido");
      const conv = await createConversation(token, {
        contact_id: contactValue,
        channel_id: channelId.trim(),
      });
      // refresh list
      const next = await listConversations(token, { limit: 50 });
      setConvs(next);
      setContactId("");
      setContactQuery("");
    } catch (e: any) {
      setError(e?.message || "Error creando conversación");
    } finally {
      setCreating(false);
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
    } catch (e: any) {
      setError(e?.message || "Error creando canal");
    } finally {
      setCreatingChannel(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Conversaciones</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <section className="space-y-2">
            <h2 className="font-medium">Lista</h2>
            {convs.length === 0 && <p className="text-slate-600">No hay conversaciones.</p>}
            <ul className="space-y-2">
              {convs.map((c) => (
                <li key={c.id}>
                  <Link className="text-blue-700 underline" href={`/conversations/${c.id}`}>
                    {c.id}
                  </Link>
                  <span className="ml-2 text-slate-600 text-sm">
                    {c.assignee ? `— ${c.assignee}` : null} {c.state ? `(${c.state})` : null}
                  </span>
                  {typeof c.unread === "number" && c.unread > 0 && (
                    <span className="ml-2 px-2 py-0.5 rounded bg-red-100 text-red-800 text-xs align-middle">{c.unread} sin leer</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h2 className="font-medium">Nueva conversación</h2>
            <div>
              <label className="block text-sm font-medium">Canal</label>
              <select
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                className="mt-1 block w-full border border-slate-300 rounded px-2 py-2"
              >
                {channels.map((ch) => (
                  <option key={ch.id} value={ch.id}>
                    {ch.phone_number || ch.id}
                  </option>
                ))}
              </select>
              {channels.length === 0 && (
                <button
                  onClick={onCreateDefaultChannel}
                  disabled={creatingChannel}
                  className="mt-2 px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60"
                >
                  {creatingChannel ? "Creando canal…" : "Crear canal por defecto"}
                </button>
              )}
            </div>
            <form onSubmit={onCreateConv} className="space-y-2">
              <label className="block text-sm font-medium">Contacto</label>
              <div className="relative">
                <input
                  value={contactQuery}
                  onChange={(e) => { setContactQuery(e.target.value); setContactId(""); }}
                  placeholder="Busca por nombre, phone o wa_id (o pega un phone)"
                  className="block w-full border border-slate-300 rounded px-3 py-2"
                  autoComplete="off"
                />
                {contactQuery.trim().length > 0 && (
                  <ul className="absolute z-10 mt-1 w-full max-h-56 overflow-auto bg-white border border-slate-200 rounded shadow-sm">
                    {contacts
                      .filter((c) => {
                        const n = contactQuery.trim().toLowerCase();
                        const fields = [c.id, c.name || "", c.phone || "", c.wa_id || ""];
                        return fields.some((f) => f.toLowerCase().includes(n));
                      })
                      .slice(0, 8)
                      .map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            onClick={() => { setContactId(c.id); setContactQuery(c.name || c.phone || c.wa_id || c.id); }}
                            className={`w-full text-left px-3 py-2 hover:bg-slate-50 ${contactId === c.id ? 'bg-slate-50' : ''}`}
                          >
                            <span className="font-medium mr-2">{c.name || c.phone || c.wa_id || c.id}</span>
                            <span className="text-slate-600 text-xs">{c.phone || "-"} · {c.wa_id || "-"}</span>
                          </button>
                        </li>
                      ))}
                    {contacts.filter((c) => {
                      const n = contactQuery.trim().toLowerCase();
                      const fields = [c.id, c.name || "", c.phone || "", c.wa_id || ""];
                      return fields.some((f) => f.toLowerCase().includes(n));
                    }).length === 0 && (
                      <li className="px-3 py-2 text-sm text-slate-600">Sin coincidencias. Puedes pegar un phone.</li>
                    )}
                  </ul>
                )}
              </div>
              {contactId && (
                <div className="text-xs text-slate-600">Seleccionado: <span className="font-mono">{contactQuery}</span> <button type="button" className="ml-2 underline" onClick={() => { setContactId(""); setContactQuery(""); }}>quitar</button></div>
              )}
              <button
                type="submit"
                disabled={creating || !channelId || (!contactId && !contactQuery.trim())}
                className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60"
              >
                {creating ? "Creando…" : "Crear"}
              </button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
