"use client";
import { useEffect, useMemo, useState } from "react";
import { Conversation, Message, createConversation, listConversations, listMessages, markRead, sendMessage, subscribeInbox } from "@/app/lib/api";

function useToken(): string | null {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    setToken(localStorage.getItem("nexia_token"));
  }, []);
  return token;
}

export default function InboxPage() {
  const token = useToken();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");

  // load conversations
  useEffect(() => {
    if (!token) return;
    listConversations(token).then(setConvs).catch(console.error);
  }, [token]);

  // load messages for selected
  const reloadMessages = async () => {
    if (!token || !selected) return;
    const msgs = await listMessages(token, selected.id, { limit: 50 });
    setMessages(msgs);
  };
  useEffect(() => { reloadMessages(); /* eslint-disable-next-line */ }, [token, selected?.id]);

  // SSE subscription: refresh on any event (simple MVP)
  useEffect(() => {
    if (!token) return;
    const stop = subscribeInbox(token, () => {
      // naive: refresh conversations/messages
      listConversations(token).then(setConvs).catch(console.error);
      reloadMessages();
    });
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selected?.id]);

  if (!token) return (
    <main>
      <p>Sin sesión. Ve a <a href="/login">/login</a></p>
    </main>
  );

  return (
    <main style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 16 }}>
      <section>
        <h2>Conversaciones</h2>
        <button onClick={async () => {
          // crea dummy convo (requiere un contact_id válido). En demo real, esto proviene de inbound.
          const contactId = prompt("contact_id?") || "ct1";
          const conv = await createConversation(token, { contact_id: contactId, channel_id: "wa_main" });
          setConvs([conv, ...convs]);
        }}>Nueva (demo)</button>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {convs.map((c) => (
            <li key={c.id}>
              <button onClick={() => setSelected(c)} style={{ width: "100%", textAlign: "left", padding: 8, background: selected?.id === c.id ? "#eef" : "#fff", border: "1px solid #ddd", margin: "8px 0" }}>
                <div><strong>{c.id}</strong></div>
                <small>{c.channel_id} · {c.state}</small>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Hilo</h2>
        {selected ? (
          <div>
            <div style={{ minHeight: 240, border: "1px solid #ddd", padding: 8, marginBottom: 8 }}>
              {messages.map((m) => (
                <div key={m.id} style={{ marginBottom: 6 }}>
                  <span style={{ fontWeight: 600 }}>{m.direction === "in" ? "←" : "→"}</span> {m.content && (m.content as any).text}
                </div>
              ))}
            </div>
            <form onSubmit={async (e) => {
              e.preventDefault();
              if (!text.trim()) return;
              await sendMessage(token!, selected.id, { type: "text", text });
              setText("");
              await reloadMessages();
            }}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Escribe un mensaje" style={{ width: "70%", marginRight: 8 }} />
              <button type="submit">Enviar</button>
              <button type="button" style={{ marginLeft: 8 }} onClick={async () => {
                await markRead(token!, selected.id, {});
                await reloadMessages();
              }}>Marcar leído</button>
            </form>
          </div>
        ) : (
          <p>Selecciona una conversación</p>
        )}
      </section>
    </main>
  );
}

