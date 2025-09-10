"use client";
import { useEffect } from "react";

export type ToastProps = {
  message: string | null;
  type?: "info" | "success" | "error";
  onClose?: () => void;
  durationMs?: number;
};

export default function Toast({ message, type = "info", onClose, durationMs = 2000 }: ToastProps) {
  useEffect(() => {
    if (!message) return;
    const id = setTimeout(() => onClose && onClose(), durationMs);
    return () => clearTimeout(id);
  }, [message, onClose, durationMs]);

  if (!message) return null;
  const styles =
    type === "success"
      ? "bg-green-600"
      : type === "error"
      ? "bg-red-600"
      : "bg-slate-800";

  return (
    <div className="fixed top-4 right-4 z-50">
      <div className={`text-white px-4 py-2 rounded shadow ${styles}`}>{message}</div>
    </div>
  );
}

