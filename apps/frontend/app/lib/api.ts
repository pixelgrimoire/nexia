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

// --- Auth real (register/login/refresh/logout) ---
export async function authRegister(email: string, password: string, orgName: string, role: "admin" | "agent" = "admin") {
  return apiFetch<{ access_token: string; refresh_token: string; token_type: string }>(
    "/api/auth/register",
    { method: "POST", body: JSON.stringify({ email, password, org_name: orgName, role }) }
  );
}

export async function authLogin(email: string, password: string) {
  return apiFetch<{ access_token: string; refresh_token: string; token_type: string }>(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );
}

export async function authRefresh(refreshToken: string) {
  return apiFetch<{ access_token: string; refresh_token: string; token_type: string }>(
    "/api/auth/refresh",
    { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) }
  );
}

export async function authLogout(token: JWT, refreshToken?: string) {
  return apiFetch<{ ok: boolean }>(
    "/api/auth/logout",
    { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
    token
  );
}

// --- Conversations ---
export type Conversation = {
  id: string;
  org_id: string;
  contact_id: string;
  channel_id: string;
  state?: string;
  assignee?: string;
  unread?: number;
};

export async function createConversation(token: JWT, body: { contact_id: string; channel_id: string; assignee?: string; state?: string }) {
  return apiFetch<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function listConversations(token: JWT, params?: { state?: string; limit?: number; include_unread?: boolean }) {
  const qs = new URLSearchParams();
  if (params?.state) qs.set("state", params.state);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.include_unread) qs.set("include_unread", "true");
  return apiFetch<Conversation[]>(`/api/conversations?${qs.toString()}`, {}, token);
}

export async function getConversation(token: JWT, id: string) {
  return apiFetch<Conversation>(`/api/conversations/${id}`, {}, token);
}

export async function updateConversation(
  token: JWT,
  id: string,
  body: { state?: string; assignee?: string | null }
) {
  return apiFetch<Conversation>(`/api/conversations/${id}`, { method: "PUT", body: JSON.stringify(body) }, token);
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

export type SendBodyText = { type: "text"; text: string; client_id?: string };
export type SendBodyTemplate = { type: "template"; template: Record<string, unknown>; client_id?: string };
export type SendBodyMedia = { type: "media"; media: { kind: "image" | "document" | "video" | "audio"; link: string; caption?: string }; client_id?: string };
export type SendBody = SendBodyText | SendBodyTemplate | SendBodyMedia;

export async function sendMessage(token: JWT, conversationId: string, body: SendBody) {
  const idem = (body as any).client_id || (typeof crypto !== "undefined" && (crypto as any).randomUUID ? (crypto as any).randomUUID() : ("cli_" + Date.now()));
  const headers: HeadersInit = { "Idempotency-Key": idem };
  return apiFetch<Message>("/api/conversations/" + conversationId + "/messages", { method: "POST", headers, body: JSON.stringify({ ...(body as any), client_id: idem }) }, token);
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

export async function getChannel(token: JWT, id: string) {
  return apiFetch<Channel>(`/api/channels/${id}`, {}, token);
}

export async function updateChannel(token: JWT, id: string, body: { type?: string; mode?: string; status?: string; phone_number?: string; credentials?: Record<string, unknown> }) {
  return apiFetch<Channel>(`/api/channels/${id}`, { method: "PUT", body: JSON.stringify(body) }, token);
}

export async function deleteChannel(token: JWT, id: string) {
  return apiFetch<{ ok: boolean }>(`/api/channels/${id}`, { method: "DELETE" }, token);
}

export async function verifyChannel(token: JWT, id: string) {
  return apiFetch<{ ok: boolean; status?: string; fake?: boolean; has_token?: boolean; phone_id?: string; match?: boolean; details?: string }>(
    `/api/channels/${id}/verify`,
    { method: "POST" },
    token
  );
}

// --- Templates ---
export type Template = {
  id: string;
  org_id: string;
  name?: string;
  language?: string;
  category?: string;
  body?: string;
  variables?: Record<string, unknown> | unknown[] | null;
  status?: string;
};

export async function listTemplates(token: JWT) {
  return apiFetch<Template[]>("/api/templates", {}, token);
}

export async function createTemplate(
  token: JWT,
  body: { name: string; language?: string; category?: string; body?: string; variables?: Record<string, unknown> | unknown[]; status?: string }
) {
  return apiFetch<Template>("/api/templates", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function getTemplate(token: JWT, id: string) {
  return apiFetch<Template>(`/api/templates/${id}`, {}, token);
}

export async function updateTemplate(
  token: JWT,
  id: string,
  body: { name?: string; language?: string; category?: string; body?: string; variables?: Record<string, unknown> | unknown[]; status?: string }
) {
  return apiFetch<Template>(`/api/templates/${id}`, { method: "PUT", body: JSON.stringify(body) }, token);
}

export async function deleteTemplate(token: JWT, id: string) {
  return apiFetch<{ ok: boolean }>(`/api/templates/${id}`, { method: "DELETE" }, token);
}

// --- Flows ---
export type Flow = {
  id: string;
  org_id: string;
  name?: string;
  version?: number;
  graph?: Record<string, unknown> | null;
  status?: string;
  created_by?: string | null;
};

export async function listFlows(token: JWT) {
  return apiFetch<Flow[]>("/api/flows", {}, token);
}

export async function createFlow(
  token: JWT,
  body: { name: string; version?: number; graph?: Record<string, unknown>; status?: string }
) {
  return apiFetch<Flow>("/api/flows", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function updateFlow(
  token: JWT,
  id: string,
  body: { name?: string; version?: number; graph?: Record<string, unknown>; status?: string }
) {
  return apiFetch<Flow>(`/api/flows/${id}`, { method: "PUT", body: JSON.stringify(body) }, token);
}

export async function deleteFlow(token: JWT, id: string) {
  return apiFetch<{ ok: boolean }>(`/api/flows/${id}`, { method: "DELETE" }, token);
}

// --- Contacts ---
export type Contact = {
  id: string;
  org_id: string;
  wa_id?: string | null;
  phone?: string | null;
  name?: string | null;
  attributes?: Record<string, unknown> | null;
  tags?: string[] | null;
  consent?: string | null;
  locale?: string | null;
  timezone?: string | null;
};

export async function listContacts(token: JWT) {
  return apiFetch<Contact[]>("/api/contacts", {}, token);
}

export async function searchContacts(
  token: JWT,
  params?: { tags?: string[]; attr_key?: string; attr_value?: string }
) {
  const qs = new URLSearchParams();
  if (params?.tags && params.tags.length) for (const t of params.tags) qs.append("tags", t);
  if (params?.attr_key) qs.set("attr_key", params.attr_key);
  if (params?.attr_value) qs.set("attr_value", params.attr_value);
  return apiFetch<Contact[]>(`/api/contacts/search?${qs.toString()}`, {}, token);
}

export async function createContact(
  token: JWT,
  body: { org_id?: string; wa_id?: string; phone?: string; name?: string; attributes?: Record<string, unknown>; tags?: string[]; consent?: string; locale?: string; timezone?: string }
) {
  return apiFetch<Contact>("/api/contacts", { method: "POST", body: JSON.stringify(body) }, token);
}

export async function getContact(token: JWT, id: string) {
  return apiFetch<Contact>(`/api/contacts/${id}`, {}, token);
}

export async function updateContact(
  token: JWT,
  id: string,
  body: { wa_id?: string; phone?: string; name?: string; attributes?: Record<string, unknown>; tags?: string[]; consent?: string; locale?: string; timezone?: string }
) {
  return apiFetch<Contact>(`/api/contacts/${id}`, { method: "PUT", body: JSON.stringify(body) }, token);
}

export async function deleteContact(token: JWT, id: string) {
  return apiFetch<{ ok: boolean }>(`/api/contacts/${id}`, { method: "DELETE" }, token);
}

// --- SSE Inbox subscription (via fetch stream) ---
// EventSource can't send Authorization headers; use fetch streaming instead.
export function subscribeInbox(
  token: JWT,
  onEvent: (data: string) => void,
  onStatus?: (s: "connecting" | "connected" | "reconnecting" | "stopped") => void,
) {
  const ctrl = new AbortController();
  const headers = new Headers({ Authorization: `Bearer ${token}`, Accept: "text/event-stream" });
  let stopped = false;

  const connect = async () => {
    let backoff = 1000; // 1s -> 15s
    while (!stopped) {
      try {
        if (onStatus) onStatus("connecting");
        const res = await fetch("/api/inbox/stream", { headers, signal: ctrl.signal });
        if (!res.body) throw new Error("no-body");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        // reset backoff after a successful connect
        backoff = 1000;
        if (onStatus) onStatus("connected");
        // Read stream
        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const chunk of parts) {
            const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
            if (dataLine) onEvent(dataLine.slice(5).trim());
          }
        }
      } catch (err: any) {
        if (stopped || (err && err.name === "AbortError")) break;
        // eslint-disable-next-line no-console
        console.warn("SSE inbox reconnect in", backoff, "ms");
        if (onStatus) onStatus("reconnecting");
        await new Promise((r) => setTimeout(r, backoff + Math.floor(Math.random() * 500)));
        backoff = Math.min(backoff * 2, 15000);
      }
    }
  };
  void connect();
  return () => {
    stopped = true;
    try { ctrl.abort(); } catch {}
    if (onStatus) onStatus("stopped");
  };
}
