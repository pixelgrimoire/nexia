"use client";
import { useEffect, useState } from "react";

type Props = {
  text: string;
  size?: number;
  className?: string;
};

export default function QRCode({ text, size = 192, className }: Props) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const QR = (await import("qrcode")).default;
        const url = await QR.toDataURL(text, { margin: 1, width: size, color: { dark: "#111111", light: "#ffffff" } });
        if (mounted) setDataUrl(url);
      } catch (e) {
        // ignore; component renders placeholder
      }
    })();
    return () => {
      mounted = false;
    };
  }, [text, size]);

  if (!dataUrl) {
    return (
      <div
        className={`flex items-center justify-center bg-white border border-slate-200 rounded ${className || ""}`}
        style={{ width: size, height: size }}
        aria-label="QR loading"
      >
        <span className="text-slate-400 text-sm">Generating QR…</span>
      </div>
    );
  }
  return <img src={dataUrl} width={size} height={size} alt="QR code" className={`bg-white border border-slate-200 rounded ${className || ""}`} />;
}

