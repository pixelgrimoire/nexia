"use client";
import { useState } from "react";
import { devLogin, getMe } from "../lib/api";
import { setTokens } from "../lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("dev@example.com");
  const [org, setOrg] = useState("Acme");
  const [role, setRole] = useState<"admin" | "agent">("admin");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await devLogin(email, org, role);
      setTokens(access_token, null);
      // sanity check
      await getMe(access_token);
      location.assign("/conversations");
    } catch (err: any) {
      setError(err?.message || "Error de autenticación");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-md mx-auto mt-10 space-y-4">
      <h1 className="text-2xl font-semibold">Login (dev)</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-sm font-medium">Email</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 block w-full border border-slate-300 rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Organización</label>
          <input
            value={org}
            onChange={(e) => setOrg(e.target.value)}
            required
            className="mt-1 block w-full border border-slate-300 rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Rol</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as any)}
            className="mt-1 block w-full border border-slate-300 rounded px-3 py-2"
          >
            <option value="admin">admin</option>
            <option value="agent">agent</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60"
        >
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
      {error && <p className="text-red-600">{error}</p>}
    </main>
  );
}
