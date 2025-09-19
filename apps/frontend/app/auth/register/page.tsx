"use client";
import { useState } from "react";
import { authRegister, getMe } from "../../lib/api";
import { setTokens } from "../../lib/auth";
import Link from "next/link";

export default function RegisterPage() {
  const [email, setEmail] = useState("admin@example.com");
  const [org, setOrg] = useState("Acme");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token, refresh_token, default_workspace_id, workspaces } = await authRegister(email, password, org, "admin");
      setTokens(access_token, refresh_token, { defaultWorkspaceId: default_workspace_id ?? null, workspaces: workspaces ?? null });
      await getMe(access_token);
      location.assign("/conversations");
    } catch (err: any) {
      setError(err?.message || "Error en registro");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-md mx-auto mt-10 space-y-4">
      <h1 className="text-2xl font-semibold">Registro</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="block text-sm font-medium">Email</label>
          <input className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="block text-sm font-medium">Organización</label>
          <input className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" value={org} onChange={(e) => setOrg(e.target.value)} required />
        </div>
        <div>
          <label className="block text-sm font-medium">Contraseña</label>
          <input type="password" className="mt-1 block w-full border border-slate-300 rounded px-3 py-2" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button type="submit" disabled={loading} className="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-60">{loading ? "Creando…" : "Crear cuenta"}</button>
      </form>
      <p className="text-sm text-slate-600">¿Ya tienes cuenta? <Link href="/auth/login" className="text-blue-700 underline">Inicia sesión</Link></p>
      {error && <p className="text-red-600">{error}</p>}
    </main>
  );
}

