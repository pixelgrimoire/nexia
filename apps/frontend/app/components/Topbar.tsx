"use client";
import { useEffect, useRef, useState } from "react";
import { authLogout, getMe, listConversations, subscribeInbox, type JWT } from "../lib/api";
import { clearTokens, getAccessToken, getRefreshToken } from "../lib/auth";
import Link from "next/link";
import Toast from "../components/Toast";
import { setupGSAP, gsap } from "../lib/gsapSetup";
import { useGSAP } from "@gsap/react";

export default function Topbar() {
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState<number>(0);
  const [sseStatus, setSseStatus] = useState<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const dotRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevStatusRef = useRef<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);
  useEffect(() => {
    const t = getAccessToken();
    if (!t) return;
    getMe(t as JWT)
      .then((u) => setEmail(String((u as any)?.email || "")))
      .catch(() => setEmail(null));
    // initial unread
    listConversations(t as JWT, { include_unread: true, limit: 200 })
      .then((rows) => setUnread(rows.reduce((acc, r: any) => acc + (r.unread || 0), 0)))
      .catch(() => {});
    // SSE subscribe
    const stop = subscribeInbox(t as JWT, () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        listConversations(t as JWT, { include_unread: true, limit: 200 })
          .then((rows) => setUnread(rows.reduce((acc, r: any) => acc + (r.unread || 0), 0)))
          .catch(() => {});
      }, 400);
    }, (s) => setSseStatus(s));
    return () => {
      if (stop) stop();
      setSseStatus("stopped");
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);
  setupGSAP();
  useGSAP(() => {
    if (!dotRef.current) return;
    gsap.killTweensOf(dotRef.current);
    if (sseStatus === "connected") {
      gsap.to(dotRef.current, { scale: 1.25, opacity: 0.8, duration: 1.2, ease: "power1.inOut", yoyo: true, repeat: -1 });
    } else {
      gsap.set(dotRef.current, { scale: 1, opacity: 0.6 });
    }
  }, { dependencies: [sseStatus] });

  // Show small toasts when reconnection cycles happen
  useEffect(() => {
    const prev = prevStatusRef.current;
    if (sseStatus === "reconnecting" && (prev === "connected" || prev === "connecting")) {
      setToast({ msg: "Reconectando SSE…", type: "info" });
    }
    if (sseStatus === "connected" && prev === "reconnecting") {
      setToast({ msg: "SSE conectado", type: "success" });
    }
    prevStatusRef.current = sseStatus;
  }, [sseStatus]);
  const onLogout = async () => {
    setLoading(true);
    setError(null);
    try {
      const t = getAccessToken();
      const r = getRefreshToken();
      if (t) await authLogout(t as JWT, r || undefined);
    } catch (e: any) {
      setError(e?.message || "error");
    } finally {
      clearTokens();
      location.assign("/auth/login");
    }
  };
  return (
    <header className="mb-4 flex items-center justify-between">
      <nav className="flex items-center gap-4">
        <Link href="/" className="font-semibold">NexIA</Link>
        <Link href="/inbox" className="text-slate-700 hover:underline">Inbox{unread > 0 ? <span className="ml-1 px-1.5 py-0.5 rounded bg-red-100 text-red-800 text-xs align-middle">{unread}</span> : null}</Link>
        <Link href="/conversations" className="text-slate-700 hover:underline">Conversaciones</Link>
        <Link href="/channels" className="text-slate-700 hover:underline">Canales</Link>
        <Link href="/connect" className="text-slate-700 hover:underline">Connect</Link>
        <Link href="/templates" className="text-slate-700 hover:underline">Plantillas</Link>
        <Link href="/flows" className="text-slate-700 hover:underline">Flujos</Link>
        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
          <span
            ref={dotRef}
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              sseStatus === 'connected' ? 'bg-green-500' : sseStatus === 'reconnecting' ? 'bg-amber-500' : 'bg-slate-400'
            }`}
          ></span>
          {sseStatus}
        </span>
      </nav>
      <div className="flex items-center gap-3 text-sm">
        {email ? <span className="text-slate-600">{email}</span> : <Link href="/auth/login" className="text-blue-700 underline">Login</Link>}
        <button onClick={onLogout} disabled={loading} className="px-2 py-1 rounded border border-slate-300">
          {loading ? "Saliendo…" : "Salir"}
        </button>
      </div>
      {error && <div className="text-red-600 text-xs">{error}</div>}
    </header>
    <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
  );
}
