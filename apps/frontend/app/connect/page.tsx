"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import QRCode from "../components/QRCode";
import { setupGSAP, gsap } from "../lib/gsapSetup";
import { useGSAP } from "@gsap/react";
import { getAccessToken } from "../lib/auth";
import { type JWT, listChannels, createChannel, verifyChannel, type Channel } from "../lib/api";
import Toast from "../components/Toast";

export default function ConnectDesktop() {
  const root = useRef<HTMLDivElement | null>(null);
  const payload = JSON.stringify({ kind: "nexia-pair", token: `pair_${Date.now()}` });
  const [token, setToken] = useState<JWT | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);

  setupGSAP();
  useGSAP(() => {
    gsap.from(".dk-card", { y: 18, opacity: 0, duration: 0.5, ease: "power2.out" });
    gsap.to(".dk-qr", { scale: 1.02, duration: 1.4, ease: "power1.inOut", yoyo: true, repeat: -1 });
  }, { scope: root });

  const hasToken = useMemo(() => Boolean(token), [token]);

  const refresh = async (t: JWT) => {
    setLoading(true);
    try {
      const rows = await listChannels(t);
      setChannels(rows);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = getAccessToken() as JWT | null;
    setToken(t);
    if (t) refresh(t);
  }, []);

  const onCreateDefault = async () => {
    if (!token) return;
    setCreating(true);
    try {
      await createChannel(token, {
        type: "whatsapp",
        mode: "cloud",
        status: "active",
        phone_number: "+10000000000",
        credentials: { phone_number_id: "wa_main" },
      });
      await refresh(token);
      setToast({ msg: "Canal creado", type: "success" });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error creando canal", type: "error" });
    } finally {
      setCreating(false);
    }
  };

  const onVerify = async (id: string) => {
    if (!token) return;
    setVerifyingId(id);
    try {
      const r = await verifyChannel(token, id);
      if (r.ok) setToast({ msg: `Verificado${r.details === 'fake-mode' ? ' (FAKE)' : ''}`, type: 'success' });
      else setToast({ msg: `Verificación incompleta${r.details ? ': ' + r.details : ''}`, type: 'error' });
    } catch (e: any) {
      setToast({ msg: e?.message || "Error verificando", type: "error" });
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <main ref={root} className="max-w-5xl mx-auto py-10 space-y-6">
      <div className="dk-card bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
        <h1 className="text-3xl font-semibold mb-6">Connect your WhatsApp</h1>
        <div className="grid md:grid-cols-2 gap-8 items-start">
          <div className="dk-qr flex justify-center">
            <QRCode text={payload} size={256} />
          </div>
          <div className="text-slate-700 space-y-4">
            <ol className="list-decimal ml-6 space-y-2">
              <li>Open WhatsApp on phone</li>
              <li>Go Settings → Linked Devices → Link a Device</li>
              <li>Scan the QR code</li>
            </ol>
            <button className="px-4 py-2.5 rounded-xl bg-emerald-600 text-white">Start Scanning</button>
            <div className="text-xs text-slate-500">Scanning for new devices…</div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6">
        <h2 className="text-xl font-semibold mb-2">WA Cloud Channel</h2>
        {!hasToken && <p className="text-red-600">Inicia sesión para gestionar canales.</p>}
        {hasToken && (
          <div className="space-y-3">
            <button onClick={onCreateDefault} disabled={creating} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">
              {creating ? "Creando…" : "Crear canal por defecto"}
            </button>
            {loading ? (
              <p>Cargando…</p>
            ) : (
              <ul className="space-y-2">
                {channels.map((c) => (
                  <li key={c.id} className="flex items-center justify-between border border-slate-200 rounded p-2">
                    <div className="text-sm">
                      <div className="font-mono">{c.phone_number || c.id}</div>
                      <div className="text-slate-600">pn_id: {(c.credentials as any)?.phone_number_id || '-'}</div>
                      <div className="text-slate-600">estado: {c.status || '-'}</div>
                    </div>
                    <button onClick={() => onVerify(c.id)} disabled={verifyingId === c.id} className="px-2 py-1 rounded border border-slate-300 text-sm">
                      {verifyingId === c.id ? 'Verificando…' : 'Verificar'}
                    </button>
                  </li>
                ))}
                {channels.length === 0 && <li className="text-slate-600 text-sm">No hay canales aún.</li>}
              </ul>
            )}
          </div>
        )}
      </div>
      <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </main>
  );
}
