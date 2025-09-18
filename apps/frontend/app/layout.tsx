import type { ReactNode } from "react";
import "./globals.css";
import Topbar from "./components/Topbar";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-slate-100 text-slate-900">
        <div className="container py-4">
          <Topbar />
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
