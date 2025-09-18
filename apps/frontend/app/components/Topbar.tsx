"use client";
import { useEffect, useRef, useState } from "react";
import { authLogout, getMe, listConversations, subscribeInbox, type JWT } from "../lib/api";
import { clearTokens, getAccessToken, getRefreshToken } from "../lib/auth";
import Link from "next/link";
import Toast from "../components/Toast";
import { setupGSAP, gsap } from "../lib/gsapSetup";
import { useGSAP } from "@gsap/react";
import { usePathname } from "next/navigation";
import { LayoutDashboard, MessageSquare, Users, Workflow, Settings, LogOut, BarChart3 } from 'lucide-react';

export default function Topbar() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<"admin" | "agent" | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState<number>(0);
  const [sseStatus, setSseStatus] = useState<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const dotRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevStatusRef = useRef<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);
  const dotColor = sseStatus === "connected" ? "bg-emerald-500" : sseStatus === "reconnecting" ? "bg-amber-500" : sseStatus === "connecting" ? "bg-slate-400" : "bg-slate-300";

  useEffect(() => {
    const t = getAccessToken();
    if (!t) return;
    getMe(t as JWT)
      .then((u) => {
        setEmail(String((u as any)?.email || ""));
        const r = String((u as any)?.role || "");
        if (r === "admin" || r === "agent") setRole(r as any);
      })
      .catch(() => setEmail(null));
    
    const fetchUnread = () => {
        listConversations(t as JWT, { include_unread: true, limit: 200 })
        .then((rows) => setUnread(rows.reduce((acc: number, r: any) => acc + (r.unread || 0), 0)))
        .catch(() => {});
    };

    fetchUnread();

    const stop = subscribeInbox(t as JWT, () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(fetchUnread, 400);
    }, (s) => setSseStatus(s));

    return () => {
      if (stop) stop();
      setSseStatus("stopped");
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const pathname = usePathname();
  const isActive = (href: string) => {
    if (!pathname) return false;
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

  setupGSAP();
  useGSAP(() => {
    if (!dotRef.current) return;
    gsap.killTweensOf(dotRef.current);
    if (sseStatus === "connected") {
      gsap.to(dotRef.current, { scale: 1.25, opacity: 0.8, duration: 1.2, ease: "power1.inOut", yoyo: true, repeat: -1 });
    } else {
      gsap.set(dotRef.current, { scale: 1, opacity: 0.6 });
    }
  }, { dependencies: [sseStatus] });

  useEffect(() => {
    const prev = prevStatusRef.current;
    if (sseStatus === "reconnecting" && (prev === "connected" || prev === "connecting")) {
      setToast({ msg: "Reconectando...", type: "info" });
    }
    if (sseStatus === "connected" && prev === "reconnecting") {
      setToast({ msg: "Conectado", type: "success" });
    }
    prevStatusRef.current = sseStatus;
  }, [sseStatus]);

  const onLogout = async () => {
    setLoading(true);
    setError(null);
    try {
      const t = getAccessToken();
      const r = getRefreshToken();
      if (t) await authLogout(t as JWT, r || undefined);
    } catch (e: any) {
      setError(e?.message || "error");
    } finally {
      clearTokens();
      location.assign("/auth/login");
    }
  };

  const navItems = [
      { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard size={18}/>, adminOnly: false },
      { href: "/inbox", label: "Inbox", icon: <MessageSquare size={18}/>, adminOnly: false },
      { href: "/contacts", label: "Contactos", icon: <Users size={18}/>, adminOnly: false },
      { href: "/flows", label: "Flujos", icon: <Workflow size={18}/>, adminOnly: true },
      { href: "/analytics", label: "Analytics", icon: <BarChart3 size={18}/>, adminOnly: true },
  ];

  const settingsItems = [
      { href: "/channels", label: "Canales", adminOnly: true },
      { href: "/templates", label: "Plantillas", adminOnly: true },
      { href: "/integrations", label: "Integraciones", adminOnly: true },
      { href: "/audit", label: "Auditoría", adminOnly: true },
      { href: "/connect", label: "Conectar", adminOnly: true },
  ]

  return (
    <>
    <header className="mb-6 flex items-center justify-between">
      <nav className="flex items-center gap-2">
        <Link href="/dashboard" className="font-bold tracking-tight text-xl mr-4">NexIA</Link>
        
        {navItems.map(item => {
            if (item.adminOnly && role !== 'admin') return null;
            const active = isActive(item.href);
            return (
                <Link key={item.href} href={item.href} 
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200"}`} 
                    aria-current={active ? "page" : undefined}>
                {item.icon}
                <span>{item.label}</span>
                {item.href === '/inbox' && unread > 0 && <span className="ml-1 px-2 py-0.5 rounded-full bg-red-500 text-white text-xs">{unread}</span>}
                </Link>
            )
        })}
      </nav>
      <div className="flex items-center gap-4 text-sm">
        {/* SSE connection status */}
        <div className="flex items-center gap-2" aria-live="polite">
          <span
            ref={dotRef}
            className={`inline-block w-2.5 h-2.5 rounded-full ${dotColor}`}
            title={sseStatus}
            aria-label={`SSE ${sseStatus}`}
          />
          <span className="hidden md:inline text-xs text-slate-500">{sseStatus}</span>
        </div>
        {email ? (
            <div className="flex items-center gap-3">
                 {(role === "admin") && (
                     <div className="group relative">
                        <button className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-slate-600 hover:bg-slate-200 transition-colors">
                            <Settings size={18}/>
                            <span>Configuración</span>
                        </button>
                        <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-xl border border-slate-200 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto">
                            {settingsItems.map(item => (
                                <Link key={item.href} href={item.href} className="block px-4 py-2 text-sm text-slate-700 hover:bg-slate-100">{item.label}</Link>
                            ))}
                        </div>
                     </div>
                 )}
                <span className="text-slate-500 hidden md:inline">{email}</span>
                <button onClick={onLogout} disabled={loading} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-slate-600 hover:bg-slate-200 transition-colors" title="Cerrar sesión">
                    <LogOut size={18} />
                    <span className="hidden md:inline">{loading ? "Saliendo…" : "Salir"}</span>
                </button>
            </div>
        ) : <Link href="/auth/login" className="text-blue-700 underline">Login</Link>}
        {error && <div className="text-red-600 text-xs">{error}</div>}
      </div>
    </header>
    <Toast message={toast?.msg || null} type={toast?.type} onClose={() => setToast(null)} />
    </>
  );
}
