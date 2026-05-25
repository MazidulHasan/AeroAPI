import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export const metadata: Metadata = {
  title: "AeroAPI",
  description: "AI-powered API testing platform"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Sidebar />
        <Topbar />
        <main className="ml-64 min-h-screen p-6">{children}</main>
      </body>
    </html>
  );
}
