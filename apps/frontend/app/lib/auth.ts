"use client";

import { authRefresh } from "./api";
import type { WorkspaceMembership } from "./api";

const ACCESS_KEY = "nexia_access";
const REFRESH_KEY = "nexia_refresh";
const WORKSPACE_ID_KEY = "nexia_workspace";
const WORKSPACES_KEY = "nexia_workspaces";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh?: string | null, opts?: { defaultWorkspaceId?: string | null; workspaces?: WorkspaceMembership[] | null }) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) {
    localStorage.setItem(REFRESH_KEY, refresh);
  } else {
    localStorage.removeItem(REFRESH_KEY);
  }
  if (opts) {
    const { defaultWorkspaceId, workspaces } = opts;
    if (workspaces) {
      try {
        localStorage.setItem(WORKSPACES_KEY, JSON.stringify(workspaces));
      } catch {
        /* ignore */
      }
    }
    if (defaultWorkspaceId !== undefined) {
      setCurrentWorkspaceId(defaultWorkspaceId ?? null);
    } else if (workspaces && workspaces.length) {
      const current = getCurrentWorkspaceId();
      if (!current || !workspaces.some((w) => w.workspace_id === current)) {
        setCurrentWorkspaceId(workspaces[0]?.workspace_id ?? null);
      }
    }
  }
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(WORKSPACE_ID_KEY);
  localStorage.removeItem(WORKSPACES_KEY);
}

export function getWorkspaceMemberships(): WorkspaceMembership[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(WORKSPACES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as WorkspaceMembership[];
  } catch {
    /* ignore */
  }
  return [];
}

export function setWorkspaceMemberships(workspaces: WorkspaceMembership[] | null) {
  if (typeof window === "undefined") return;
  if (!workspaces || !workspaces.length) {
    localStorage.removeItem(WORKSPACES_KEY);
    return;
  }
  try {
    localStorage.setItem(WORKSPACES_KEY, JSON.stringify(workspaces));
  } catch {
    /* ignore */
  }
}

export function getCurrentWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  const value = localStorage.getItem(WORKSPACE_ID_KEY);
  return value || null;
}

export function setCurrentWorkspaceId(id: string | null) {
  if (typeof window === "undefined") return;
  if (id) {
    localStorage.setItem(WORKSPACE_ID_KEY, id);
  } else {
    localStorage.removeItem(WORKSPACE_ID_KEY);
  }
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
    setTokens(rr.access_token, rr.refresh_token, {
      defaultWorkspaceId: rr.default_workspace_id ?? null,
      workspaces: rr.workspaces ?? null,
    });
    if (rr.workspaces) setWorkspaceMemberships(rr.workspaces);
    if (rr.default_workspace_id !== undefined) setCurrentWorkspaceId(rr.default_workspace_id ?? null);
    const h2 = new Headers(init?.headers || {});
    h2.set("Authorization", `Bearer ${rr.access_token}`);
    res = await fetch(input, { ...init, headers: h2 });
  } catch {
    // ignore; caller will handle 401
  }
  return res;
}

