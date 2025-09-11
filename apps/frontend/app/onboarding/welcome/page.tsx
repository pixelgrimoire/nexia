"use client";
import Link from "next/link";
import { useRef } from "react";
import { setupGSAP, gsap } from "../../lib/gsapSetup";
import { useGSAP } from "@gsap/react";

function Card({ icon, title, subtitle }: { icon: string; title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-lg border border-slate-200 bg-white shadow-sm">
      <span className="text-2xl" aria-hidden>
        {icon}
      </span>
      <div>
        <div className="font-medium">{title}</div>
        <div className="text-slate-600 text-sm">{subtitle}</div>
      </div>
    </div>
  );
}

export default function OnboardingWelcome() {
  const root = useRef<HTMLDivElement | null>(null);
  setupGSAP();
  useGSAP(() => {
    gsap.from(".ob-title", { y: 14, opacity: 0, duration: 0.45, ease: "power2.out" });
    gsap.from(".ob-card-item", { y: 12, opacity: 0, duration: 0.35, ease: "power2.out", stagger: 0.08 });
    gsap.from(".ob-cta", { y: 12, opacity: 0, duration: 0.4, ease: "power2.out", delay: 0.1 });
  }, { scope: root });
  return (
    <main ref={root} className="max-w-md mx-auto py-10">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-6">
        <div className="ob-title text-center space-y-1">
          <h1 className="text-3xl font-semibold">Welcome to NexIA!</h1>
          <p className="text-slate-600">Automate WhatsApp, grow your business.</p>
        </div>
        <div className="space-y-3">
          <div className="ob-card-item"><Card icon="⏱️" title="Save Time" subtitle="Automated replies and flows" /></div>
          <div className="ob-card-item"><Card icon="🛡️" title="24/7 Professionalism" subtitle="Consistent, compliant responses" /></div>
        </div>
        <p className="ob-cta">
          <Link href="/onboarding/connect" className="inline-flex justify-center items-center w-full px-4 py-2.5 rounded-xl bg-slate-900 text-white">Let's Connect WhatsApp</Link>
        </p>
      </div>
    </main>
  );
}
