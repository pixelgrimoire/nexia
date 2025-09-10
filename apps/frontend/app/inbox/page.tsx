"use client";
import { useEffect, useRef, useState } from "react";
import { subscribeInbox } from "../lib/api";

export default function InboxPage() {
  const [events, setEvents] = useState<string[]>([]);
  const [hasToken, setHasToken] = useState<boolean>(false);
  const stopRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    const token = localStorage.getItem("nexia_token");
    setHasToken(!!token);
    if (!token) return;
    stopRef.current = subscribeInbox(token, (data) => {
      setEvents((prev) => [data, ...prev].slice(0, 50));
    });
    return () => {
      if (stopRef.current) stopRef.current();
    };
  }, []);

  return (
    <main>
      <h1>Inbox (SSE)</h1>
      {!hasToken && (
        <p style={{ color: "#a00" }}>Token no encontrado. Ve a /login primero.</p>
      )}
      <ul>
        {events.map((e, i) => (
          <li key={i} style={{ fontFamily: "monospace" }}>
            {e}
          </li>
        ))}
      </ul>
    </main>
  );
}
