"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Toast from "../components/Toast";
import {
  type JWT,
  type Conversation,
  listConversations,
  markRead,
  subscribeInbox,
} from "../lib/api";
import { getAccessToken } from "../lib/auth";

export default function InboxPage() {
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [stateFilter, setStateFilter] = useState<string>("");
  const [q, setQ] = useState("");
  const stopRef = useRef<null | (() => void)>(null);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const load = async (t: JWT) => {
    setLoading(true);
    setError(null);
    try {
      const list = await listConversations(t, { limit: 200, state: stateFilter || undefined, include_unread: true });
      setConvs(list);
    } catch (e: any) {
      setError(e?.message || "Error cargando inbox");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = getAccessToken() as JWT | null;
    setToken(t);
    if (!t) {
      router.push("/auth/login");
      return;
    }
    load(t);
    // Subscribe SSE
    stopRef.current = subscribeInbox(t, () => {
      load(t);
    });
    return () => {
      if (stopRef.current) stopRef.current();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateFilter]);

  const filtered = convs.filter((c) => {
    if (!q.trim()) return true;
    const needle = q.trim().toLowerCase();
    return (
      c.id.toLowerCase().includes(needle) ||
      (c.channel_id || "").toLowerCase().includes(needle) ||
      (c.contact_id || "").toLowerCase().includes(needle)
    );
  });

  const onMarkRead = async (id: string) => {
    if (!token) return;
    try {
      await markRead(token, id, {});
      await load(token);
      setToast({ msg: "Marcado como leído", type: "success" });
    } catch (e) {
      // ignore
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Inbox</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
      <div className="flex gap-2 items-center">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…" className="border border-slate-300 rounded px-3 py-2" />
        <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)} className="border border-slate-300 rounded px-3 py-2">
          <option value="">(todos)</option>
          <option value="open">open</option>
          <option value="pending">pending</option>
          <option value="closed">closed</option>
        </select>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <ul className="space-y-2">
          {filtered.map((c) => (
            <li key={c.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
              <div className="text-sm">
                <Link href={`/conversations/${c.id}`} className="text-blue-700 underline">{c.id}</Link>
                <span className="ml-2 text-slate-600">{c.channel_id} · {c.state}</span>
              </div>
              <div className="flex items-center gap-3">
                {typeof c.unread === "number" && c.unread > 0 && (
                  <span className="px-2 py-0.5 rounded bg-red-100 text-red-800 text-xs">{c.unread} sin leer</span>
                )}
                <button onClick={() => onMarkRead(c.id)} className="px-2 py-1 rounded border border-slate-300 text-sm">Marcar leído</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}
