"use client";
import { useEffect, useState } from "react";
import { authLogout, getMe, type JWT } from "../lib/api";
import { clearTokens, getAccessToken, getRefreshToken } from "../lib/auth";
import Link from "next/link";

export default function Topbar() {
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const t = getAccessToken();
    if (!t) return;
    getMe(t as JWT)
      .then((u) => setEmail(String((u as any)?.email || "")))
      .catch(() => setEmail(null));
  }, []);
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
        <Link href="/inbox" className="text-slate-700 hover:underline">Inbox</Link>
        <Link href="/conversations" className="text-slate-700 hover:underline">Conversaciones</Link>
        <Link href="/channels" className="text-slate-700 hover:underline">Canales</Link>
      </nav>
      <div className="flex items-center gap-3 text-sm">
        {email ? <span className="text-slate-600">{email}</span> : <Link href="/auth/login" className="text-blue-700 underline">Login</Link>}
        <button onClick={onLogout} disabled={loading} className="px-2 py-1 rounded border border-slate-300">
          {loading ? "Saliendo…" : "Salir"}
        </button>
      </div>
      {error && <div className="text-red-600 text-xs">{error}</div>}
    </header>
  );
}
