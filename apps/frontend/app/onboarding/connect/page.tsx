"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import QRCode from "../../components/QRCode";
import { setupGSAP, gsap } from "../../lib/gsapSetup";
import { useGSAP } from "@gsap/react";

export default function OnboardingConnect() {
  const root = useRef<HTMLDivElement | null>(null);
  const [scanning, setScanning] = useState(false);
  const payload = useMemo(() => {
    const token = typeof crypto !== "undefined" && (crypto as any).randomUUID ? (crypto as any).randomUUID() : `pair_${Date.now()}`;
    return JSON.stringify({ kind: "nexia-pair", token });
  }, []);

  // Animations
  setupGSAP();
  useGSAP(() => {
    gsap.from(".ob-qr-card", { y: 16, opacity: 0, duration: 0.5, ease: "power2.out" });
    // subtle QR pulse
    gsap.to(".ob-qr", { scale: 1.025, duration: 1.2, ease: "power1.inOut", yoyo: true, repeat: -1 });
  }, { scope: root });

  // scanning button feedback
  useEffect(() => {
    if (!root.current) return;
    const btn = root.current.querySelector(".ob-scan-btn");
    if (!btn) return;
    gsap.killTweensOf(btn);
    if (scanning) {
      gsap.to(btn, { y: -2, duration: 0.4, ease: "power1.inOut", yoyo: true, repeat: -1 });
    } else {
      gsap.set(btn, { y: 0 });
    }
  }, [scanning]);

  return (
    <main ref={root} className="max-w-md mx-auto py-10">
      <div className="ob-qr-card bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-semibold">Connect your WhatsApp</h1>
          <span aria-label="security" title="Secure" className="text-slate-500">🔒</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="ob-qr"><QRCode text={payload} size={208} /></div>
          <div className="text-sm text-slate-700">
            <ol className="list-decimal ml-5 space-y-1">
              <li>Open WhatsApp on phone</li>
              <li>Go Settings → Linked Devices → Link a Device</li>
              <li>Scan this QR code</li>
            </ol>
          </div>
        </div>
        <div className="space-y-2">
          <button onClick={() => setScanning((v) => !v)} className="ob-scan-btn w-full px-4 py-2.5 rounded-xl bg-emerald-600 text-white">{scanning ? "Scanning…" : "Start Scanning"}</button>
          <p className="text-xs text-slate-500 text-center">{scanning ? "Scanning for new devices…" : "Ready to link a device"}</p>
        </div>
        <p className="text-sm text-slate-600 text-center">
          Prefer desktop? Try the <Link href="/connect" className="text-blue-700 underline">desktop connect</Link> screen.
        </p>
      </div>
    </main>
  );
}
