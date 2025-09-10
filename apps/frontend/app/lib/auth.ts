"use client";

import { authRefresh } from "./api";

const ACCESS_KEY = "nexia_access";
const REFRESH_KEY = "nexia_refresh";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh?: string | null) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// Fetch helper with auto-refresh on 401
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const access = getAccessToken();
  const headers = new Headers(init?.headers || {});
  if (access) headers.set("Authorization", `Bearer ${access}`);
  let res = await fetch(input, { ...init, headers });
  if (res.status !== 401) return res;
  // try refresh
  const refresh = getRefreshToken();
  if (!refresh) return res;
  try {
    const rr = await authRefresh(refresh);
    setTokens(rr.access_token, rr.refresh_token);
    const h2 = new Headers(init?.headers || {});
    h2.set("Authorization", `Bearer ${rr.access_token}`);
    res = await fetch(input, { ...init, headers: h2 });
  } catch {
    // ignore; caller will handle 401
  }
  return res;
}

