"use client";
import { useEffect, useRef } from "react";
import QRCode from "../components/QRCode";
import { setupGSAP, gsap } from "../lib/gsapSetup";
import { useGSAP } from "@gsap/react";

export default function ConnectDesktop() {
  const root = useRef<HTMLDivElement | null>(null);
  const payload = JSON.stringify({ kind: "nexia-pair", token: `pair_${Date.now()}` });
  setupGSAP();
  useGSAP(() => {
    gsap.from(".dk-card", { y: 18, opacity: 0, duration: 0.5, ease: "power2.out" });
    gsap.to(".dk-qr", { scale: 1.02, duration: 1.4, ease: "power1.inOut", yoyo: true, repeat: -1 });
  }, { scope: root });
  useEffect(() => {}, []);
  return (
    <main ref={root} className="max-w-4xl mx-auto py-10">
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
    </main>
  );
}
