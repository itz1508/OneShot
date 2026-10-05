import type { Metadata } from "next";
import "./globals.css";
import { RsmRail } from "@/features/rsm-rail/RsmRail";

export const metadata: Metadata = {
  title: "RSM — Replay State Memory",
  description: "Local-first UI onto the authoritative RSM daemon.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <div className="flex-1">{children}</div>
        <RsmRail />
      </body>
    </html>
  );
}
