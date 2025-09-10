"use client";
import { useState } from "react";
import { devLogin, getMe } from "../lib/api";

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
      localStorage.setItem("nexia_token", access_token);
      // sanity check
      await getMe(access_token);
      location.assign("/inbox");
    } catch (err: any) {
      setError(err?.message || "Error de autenticación");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ maxWidth: 420, margin: "40px auto" }}>
      <h1>Login (dev)</h1>
      <form onSubmit={onSubmit}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} required style={{ display: "block", width: "100%", marginBottom: 8 }} />
        </label>
        <label>
          Organización
          <input value={org} onChange={(e) => setOrg(e.target.value)} required style={{ display: "block", width: "100%", marginBottom: 8 }} />
        </label>
        <label>
          Rol
          <select value={role} onChange={(e) => setRole(e.target.value as any)} style={{ display: "block", width: "100%", marginBottom: 16 }}>
            <option value="admin">admin</option>
            <option value="agent">agent</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </main>
  );
}
