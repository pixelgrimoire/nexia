"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { authRegister, getMe } from "../../lib/api";
import { setTokens } from "../../lib/auth";
import { setupGSAP, gsap } from "../../lib/gsapSetup";
import { useGSAP } from "@gsap/react";

export default function OnboardingStart() {
  const root = useRef<HTMLDivElement | null>(null);
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Animations
  setupGSAP();
  useGSAP(() => {
    gsap.from(".ob-card", { y: 16, opacity: 0, duration: 0.5, ease: "power2.out" });
    gsap.from(".ob-input", { y: 10, opacity: 0, duration: 0.35, ease: "power2.out", stagger: 0.06, delay: 0.05 });
    gsap.from(".ob-cta", { y: 12, opacity: 0, duration: 0.4, ease: "power2.out", delay: 0.15 });
  }, { scope: root });

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw !== pw2) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { access_token, refresh_token } = await authRegister(email.trim(), pw, org.trim(), "admin");
      setTokens(access_token, refresh_token);
      await getMe(access_token);
      location.assign("/onboarding/welcome");
    } catch (e: any) {
      setError(e?.message || "Error creating account");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main ref={root} className="max-w-md mx-auto py-10">
      <div className="ob-card bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-semibold">Get Started with NexIA</h1>
          <span aria-label="security" title="Secure" className="text-slate-500">🔒</span>
        </div>
        <form onSubmit={onSubmit} className="space-y-3">
          <input placeholder="Work Email" className="ob-input w-full border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 focus:bg-white" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input placeholder="Create Password" type="password" className="ob-input w-full border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 focus:bg-white" value={pw} onChange={(e) => setPw(e.target.value)} required />
          <input placeholder="Create Password" type="password" className="ob-input w-full border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 focus:bg-white" value={pw2} onChange={(e) => setPw2(e.target.value)} required />
          <input placeholder="Business Name" className="ob-input w-full border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 focus:bg-white" value={org} onChange={(e) => setOrg(e.target.value)} required />
          <button type="submit" disabled={loading} className="ob-cta w-full px-4 py-2.5 rounded-xl bg-slate-900 text-white disabled:opacity-60">{loading ? "Creating…" : "Create Account"}</button>
        </form>
        <p className="text-sm text-slate-600 text-center">Already have an account? <Link className="text-blue-700 underline" href="/auth/login">Log in</Link></p>
        {error && <p className="text-red-600 text-center">{error}</p>}
      </div>
    </main>
  );
}
