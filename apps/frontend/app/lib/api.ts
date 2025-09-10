// Simple API helpers for NexIA frontend (MVP)

export type JWT = string;

const base = ""; // same-origin proxy via Traefik

async function apiFetch<T>(path: string, opts: RequestInit = {}, token?: JWT): Promise<T> {
  const headers = new Headers(opts.headers || {});
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(base + path, { ...opts, headers });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(`API ${res.status}: ${JSON.stringify(body)}`);
  }
  return (await safeJson(res)) as T;
}

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

// --- Auth (dev) ---
export async function devLogin(email: string, orgName: string, role: "admin" | "agent" = "admin") {
  return apiFetch<{ access_token: string; token_type: string }>(
    "/api/auth/dev-login",
    { method: "POST", body: JSON.stringify({ email, org_name: orgName, role }) }
  );
}

export async function getMe(token: JWT) {
  return apiFetch<Record<string, unknown>>("/api/me", {}, token);
}

// --- Conversations ---
export type Conversation = {
  id: string;
  org_id: string;
  contact_id: string;
  channel_id: string;
  state?: string;
  assignee?: string;
};

export async function createConversation(token: JWT, body: { contact_id: string; channel_id: string; assignee?: string; state?: string }) {
  return apiFetch<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function listConversations(token: JWT, params?: { state?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.state) qs.set("state", params.state);
  if (params?.limit) qs.set("limit", String(params.limit));
  return apiFetch<Conversation[]>(`/api/conversations?${qs.toString()}`, {}, token);
}

export type Message = {
  id: string;
  conversation_id: string;
  direction: "in" | "out" | string;
  type: string;
  content?: Record<string, unknown> | null;
  client_id?: string | null;
  status?: string | null;
  meta?: Record<string, unknown> | null;
};

export async function listMessages(
  token: JWT,
  conversationId: string,
  params?: { limit?: number; offset?: number; after_id?: string }
) {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.after_id) qs.set("after_id", params.after_id);
  return apiFetch<Message[]>(`/api/conversations/${conversationId}/messages?${qs.toString()}`, {}, token);
}

export async function sendMessage(token: JWT, conversationId: string, body: { type: "text"; text: string; client_id?: string }) {
  return apiFetch<Message>(`/api/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify(body) }, token);
}

export async function markRead(token: JWT, conversationId: string, body?: { up_to_id?: string }) {
  return apiFetch<{ updated: number }>(`/api/conversations/${conversationId}/messages/read`, { method: "POST", body: JSON.stringify(body || {}) }, token);
}

// --- Channels ---
export type Channel = {
  id: string;
  org_id: string;
  type?: string;
  mode?: string;
  status?: string;
  phone_number?: string;
  credentials?: Record<string, unknown>;
};

export async function createChannel(token: JWT, body: { type?: string; mode?: string; status?: string; phone_number?: string; credentials?: Record<string, unknown> }) {
  return apiFetch<Channel>("/api/channels", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function listChannels(token: JWT) {
  return apiFetch<Channel[]>("/api/channels", {}, token);
}

// --- SSE Inbox subscription (via fetch stream) ---
// EventSource can't send Authorization headers; use fetch streaming instead.
export function subscribeInbox(token: JWT, onEvent: (data: string) => void) {
  const ctrl = new AbortController();
  const headers = new Headers({ Authorization: `Bearer ${token}`, Accept: "text/event-stream" });
  fetch("/api/inbox/stream", { headers, signal: ctrl.signal }).then(async (res) => {
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Split SSE events on double newlines
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const chunk of parts) {
        // extract last data: line
        const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
        if (dataLine) onEvent(dataLine.slice(5).trim());
      }
    }
  });
  return () => ctrl.abort();
}
