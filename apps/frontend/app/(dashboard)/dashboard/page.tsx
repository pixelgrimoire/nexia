"use client";
import { useEffect, useState } from "react";

type Status = {
  rate_limit?: { enabled?: boolean; per_min?: number; limited?: number };
  idempotency?: { reuse?: number };
};

function parsePromMetric(text: string, name: string): number | null {
  try {
    const lines = text.split(/\n+/);
    const line = lines.find((l) => l.startsWith(name + " ")) || lines.find((l) => l.startsWith(name + "{"));
    if (!line) return null;
    const parts = line.trim().split(/\s+/);
    const val = parseFloat(parts[parts.length - 1]);
    return isFinite(val) ? val : null;
  } catch {
    return null;
  }
}

export default function DashboardPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [blocked, setBlocked] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setErr(null);
        // status JSON (no auth middleware for this route)
        const sres = await fetch("/internal/status");
        const sjson = sres.ok ? await sres.json() : {};
        if (!alive) return;
        setStatus(sjson as Status);
      } catch (e: any) {
        if (!alive) return;
        setErr("Error obteniendo estado interno");
      }
      try {
        const mres = await fetch("/metrics");
        const mtext = await mres.text();
        if (!alive) return;
        setBlocked(parsePromMetric(mtext, "nexia_api_gateway_window_blocked_total"));
      } catch (e: any) {
        if (!alive) return;
        setErr((prev) => prev || "Error leyendo métricas");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      {err && <p className="text-red-600">{err}</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded border border-slate-200 p-3">
          <div className="text-sm text-slate-500">24h window bloqueos</div>
          <div className="text-2xl font-semibold">{blocked ?? "—"}</div>
        </div>
        <div className="rounded border border-slate-200 p-3">
          <div className="text-sm text-slate-500">Rate limit (min)</div>
          <div className="text-lg">{status?.rate_limit?.per_min ?? "—"}</div>
          <div className="text-xs text-slate-500">limited: {status?.rate_limit?.limited ?? 0}</div>
        </div>
        <div className="rounded border border-slate-200 p-3">
          <div className="text-sm text-slate-500">Idempotency reusos</div>
          <div className="text-2xl font-semibold">{status?.idempotency?.reuse ?? 0}</div>
        </div>
      </div>
    </main>
  );
}
