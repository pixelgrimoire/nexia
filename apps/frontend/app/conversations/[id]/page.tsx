"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Toast from "../../components/Toast";
import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import {
  type JWT,
  listMessages,
  sendMessage,
  type Message,
  subscribeInbox,
} from "../../lib/api";
import { getAccessToken } from "../../lib/auth";

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const convId = params?.id as string;
  const router = useRouter();
  const [token, setToken] = useState<JWT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [msgType, setMsgType] = useState<"text" | "template" | "media">("text");
  const [tplName, setTplName] = useState("");
  const [tplLang, setTplLang] = useState("es");
  const [mediaKind, setMediaKind] = useState<"image" | "document" | "video" | "audio">("image");
  const [mediaLink, setMediaLink] = useState("");
  const [mediaCaption, setMediaCaption] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  useEffect(() => {
    setToken(getAccessToken() as JWT | null);
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

  // Simple route protection: if no token, redirect to /auth/login
  useEffect(() => {
    if (token === null) return; // still resolving
    if (!token) router.push("/auth/login");
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
    if (!token || !convId) return;
    setSending(true);
    setError(null);
    try {
      let payload: any;
      if (msgType === "text") {
        if (!text.trim()) throw new Error("Texto requerido");
        payload = { type: "text", text: text.trim() };
      } else if (msgType === "template") {
        if (!tplName.trim()) throw new Error("Nombre de plantilla requerido");
        payload = { type: "template", template: { name: tplName.trim(), language: { code: tplLang.trim() || "es" }, components: [] } };
      } else {
        if (!mediaLink.trim()) throw new Error("Link de media requerido");
        payload = { type: "media", media: { kind: mediaKind, link: mediaLink.trim(), caption: mediaCaption || undefined } };
      }
      await sendMessage(token, convId, payload);
      setText(""); setMediaLink(""); setMediaCaption("");
      await load();
      setToast({ msg: "Mensaje enviado", type: "success" });
    } catch (e: any) {
      const msg = String(e?.message || "Error enviando");
      // Detect 24h window enforcement from API (HTTP 422)
      if (msg.includes("422") || msg.toLowerCase().includes("outside-24h-window")) {
        setMsgType("template");
        setToast({ msg: "Fuera de la ventana de 24h: usa una plantilla aprobada", type: "error" });
        setError("Fuera de 24h — cambia a plantilla");
      } else {
        setError(msg);
        setToast({ msg: "Error enviando", type: "error" });
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Conversación {convId}</h1>
      {!hasToken && <p className="text-red-600">Ve a /auth/login primero.</p>}
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
          <form onSubmit={onSend} className="space-y-2">
            <div className="flex gap-2 items-center">
              <select value={msgType} onChange={(e) => setMsgType(e.target.value as any)} className="border border-slate-300 rounded px-3 py-2">
                <option value="text">texto</option>
                <option value="template">plantilla</option>
                <option value="media">media</option>
              </select>
              {msgType === "text" && (
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Escribe un mensaje…" className="flex-1 border border-slate-300 rounded px-3 py-2" />
              )}
            </div>
            {msgType === "template" && (
              <div className="flex gap-2">
                <input value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="nombre plantilla" className="flex-1 border border-slate-300 rounded px-3 py-2" />
                <input value={tplLang} onChange={(e) => setTplLang(e.target.value)} placeholder="idioma (es)" className="w-32 border border-slate-300 rounded px-3 py-2" />
              </div>
            )}
            {msgType === "media" && (
              <div className="flex gap-2">
                <select value={mediaKind} onChange={(e) => setMediaKind(e.target.value as any)} className="border border-slate-300 rounded px-3 py-2">
                  <option value="image">image</option>
                  <option value="document">document</option>
                  <option value="video">video</option>
                  <option value="audio">audio</option>
                </select>
                <input value={mediaLink} onChange={(e) => setMediaLink(e.target.value)} placeholder="https://..." className="flex-1 border border-slate-300 rounded px-3 py-2" />
                <input value={mediaCaption} onChange={(e) => setMediaCaption(e.target.value)} placeholder="caption (opcional)" className="flex-1 border border-slate-300 rounded px-3 py-2" />
              </div>
            )}
            <div className="flex gap-2">
              <button type="submit" disabled={sending || (msgType === 'text' && !text.trim()) || (msgType === 'template' && !tplName.trim()) || (msgType === 'media' && !mediaLink.trim())} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{sending ? "Enviando…" : "Enviar"}</button>
              <button type="button" onClick={load} className="px-3 py-2 rounded border border-slate-300">Refrescar</button>
            </div>
          </form>
        </>
      )}
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}
