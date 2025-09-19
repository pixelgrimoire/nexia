"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { authLogout, getMe, listConversations, subscribeInbox, type JWT } from "../lib/api";
import { clearTokens, getAccessToken, getRefreshToken } from "../lib/auth";
import Link from "next/link";
import Toast from "../components/Toast";
import { setupGSAP, gsap } from "../lib/gsapSetup";
import { useGSAP } from "@gsap/react";
import { usePathname } from "next/navigation";
import { LayoutDashboard, MessageSquare, Users, Workflow, Settings, LogOut, BarChart3, ScrollText } from 'lucide-react';

export default function Topbar() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<"owner" | "admin" | "agent" | "analyst" | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState<number>(0);
  const [sseStatus, setSseStatus] = useState<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const dotRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevStatusRef = useRef<"connecting" | "connected" | "reconnecting" | "stopped">("stopped");
  const settingsRef = useRef<HTMLDivElement | null>(null);
  const stopSubscriptionRef = useRef<(() => void) | null>(null);
  const [toast, setToast] = useState<{ msg: string; type?: "info" | "success" | "error" } | null>(null);
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const fetchUnread = useCallback((token: JWT) => {
    listConversations(token, { include_unread: true, limit: 200 })
      .then((rows) => setUnread(rows.reduce((acc: number, r: any) => acc + (r.unread || 0), 0)))
      .catch(() => {});
  }, []);
  const dotColor = sseStatus === "connected" ? "bg-emerald-500" : sseStatus === "reconnecting" ? "bg-amber-500" : sseStatus === "connecting" ? "bg-slate-400" : "bg-slate-300";

  useEffect(() => {
    const token = getAccessToken() as JWT | null;
    if (!token) return;

    let cancelled = false;

    getMe(token)
      .then((u) => {
        if (cancelled) return;
        setEmail(String((u as any)?.email || ""));
        const r = String((u as any)?.role || "");
        if (r === "owner" || r === "admin" || r === "agent" || r === "analyst") {
          setRole(r as any);
          if (r === "owner" || r === "admin" || r === "agent") fetchUnread(token);
        }
      })
      .catch(() => {
        if (!cancelled) setEmail(null);
      });

    return () => {
      cancelled = true;
    };
  }, [fetchUnread]);

  useEffect(() => {
    const token = getAccessToken() as JWT | null;
    if (!token) return;

    const allowedInbox = role === "admin" || role === "agent" || role === "owner";

    if (!allowedInbox) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (stopSubscriptionRef.current) {
        stopSubscriptionRef.current();
        stopSubscriptionRef.current = null;
      }
      setSseStatus("stopped");
      return;
    }

    if (stopSubscriptionRef.current) {
      stopSubscriptionRef.current();
      stopSubscriptionRef.current = null;
    }

    const stop = subscribeInbox(
      token,
      () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => fetchUnread(token), 400);
      },
      (s) => setSseStatus(s)
    );
    stopSubscriptionRef.current = stop;

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (stopSubscriptionRef.current) {
        stopSubscriptionRef.current();
        stopSubscriptionRef.current = null;
      }
    };
  }, [role, fetchUnread]);

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

  useEffect(() => {
    const handleClick = (ev: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(ev.target as Node)) {
        setShowSettingsMenu(false);
      }
    };
    const handleKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setShowSettingsMenu(false);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, []);

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
      { href: "/audit", label: "Auditoría", icon: <ScrollText size={18}/>, adminOnly: true },
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
            // Admin-only items are visible to admin/owner; allow analyst to see Analytics/Auditoría
            if (item.adminOnly && !(role === 'admin' || role === 'owner' || (role === 'analyst' && (item.href === '/analytics' || item.href === '/audit')))) return null;
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
                 {(role === "admin" || role === "owner") && (
                     <div
                        className="relative"
                        onMouseEnter={() => setShowSettingsMenu(true)}
                        onMouseLeave={() => setShowSettingsMenu(false)}
                        ref={settingsRef}
                      >
                        <button
                          type="button"
                          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-slate-600 hover:bg-slate-200 transition-colors"
                          aria-haspopup="true"
                          aria-expanded={showSettingsMenu}
                          onClick={() => setShowSettingsMenu((prev) => !prev)}
                        >
                            <Settings size={18}/>
                            <span>Configuración</span>
                        </button>
                        <div
                          className={`absolute right-0 w-48 bg-white rounded-lg shadow-xl border border-slate-200 py-1 transition-opacity ${showSettingsMenu ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
                          role="menu"
                        >
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
