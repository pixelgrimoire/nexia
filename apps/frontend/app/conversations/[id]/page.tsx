"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import {
  type JWT,
  listMessages,
  sendMessage,
  type Message,
  subscribeInbox,
} from "../../lib/api";

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const convId = params?.id as string;
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setToken(localStorage.getItem("nexia_token") as JWT | null);
  }, []);

  const hasToken = useMemo(() => Boolean(token), [token]);

  const load = async () => {
    if (!token || !convId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listMessages(token, convId, { limit: 50 });
      setMsgs(data);
    } catch (e: any) {
      setError(e?.message || "Error cargando mensajes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, convId]);

  // Simple route protection: if no token, redirect to /login
  useEffect(() => {
    if (token === null) return; // still resolving
    if (!token) router.push("/login");
  }, [token, router]);

  // SSE auto-refresh on inbox events
  useEffect(() => {
    if (!token) return;
    const stop = subscribeInbox(token, () => {
      // naive refresh on any event
      load();
    });
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, convId]);

  // auto-scroll to bottom on new messages
  useEffect(() => {
    if (!listRef.current) return;
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [msgs.length]);

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !convId || !text.trim()) return;
    setSending(true);
    setError(null);
    try {
      await sendMessage(token, convId, { type: "text", text: text.trim() });
      setText("");
      await load();
    } catch (e: any) {
      setError(e?.message || "Error enviando");
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Conversación {convId}</h1>
      {!hasToken && <p className="text-red-600">Ve a /login primero.</p>}
      {error && <p className="text-red-600">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <>
          <div ref={listRef} className="min-h-[240px] max-h-[60vh] overflow-auto border border-slate-200 rounded p-2">
          <ul className="list-none p-0 space-y-2">
            {msgs.map((m) => (
              <li key={m.id} className="flex items-start gap-2">
                <span className="opacity-60 shrink-0">{m.direction === "in" ? "←" : "→"}</span>
                <span className="text-sm">
                  <span className="px-1 py-0.5 rounded bg-slate-200 mr-2 align-middle text-xs">{m.type}</span>
                  {m.content ? JSON.stringify(m.content) : null}
                  {m.direction !== "in" && (
                    <span className="ml-2 text-xs align-middle">
                      {/* Status chip based on meta.wa_msg_id when available */}
                      {m.meta && (m.meta as any).wa_msg_id ? (
                        <span className="px-1.5 py-0.5 rounded bg-green-100 text-green-800">entregado</span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">enviado</span>
                      )}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
          </div>
          <form onSubmit={onSend} className="flex gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Escribe un mensaje…"
              className="flex-1 border border-slate-300 rounded px-3 py-2"
            />
            <button
              type="submit"
              disabled={sending || !text.trim()}
              className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60"
            >
              {sending ? "Enviando…" : "Enviar"}
            </button>
            <button type="button" onClick={load} className="px-3 py-2 rounded border border-slate-300">
              Refrescar
            </button>
          </form>
        </>
      )}
    </main>
  );
}
