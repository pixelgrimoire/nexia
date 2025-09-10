"use client";
import Link from "next/link";
import { useRef } from "react";
import { setupGSAP, gsap } from "./lib/gsapSetup";
import { useGSAP } from "@gsap/react";

export default function HomePage() {
  const root = useRef<HTMLDivElement | null>(null);
  setupGSAP();
  useGSAP(() => {
    gsap.from("h1", { y: 12, opacity: 0, duration: 0.6, ease: "power2.out" });
  }, { scope: root });

  return (
    <main ref={root} className="space-y-3">
      <h1 className="text-2xl font-semibold">NexIA</h1>
      <p className="text-slate-700">Frontend (MVP) listo. Inicia sesión de desarrollo:</p>
      <p>
        <Link className="inline-flex items-center rounded-md bg-slate-900 text-white px-3 py-1 text-sm" href="/login">Ir a Login (dev)</Link>
      </p>
    </main>
  );
}
