"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, PlayCircle, Settings, ShieldCheck } from "lucide-react";

const nav = [
  { href: "/", label: "Dashboard", icon: BarChart3 },
  { href: "/new-run", label: "New Run", icon: PlayCircle },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings }
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="fixed left-0 top-0 z-20 h-screen w-64 border-r border-line bg-white">
      <div className="flex h-16 items-center gap-3 border-b border-line px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded bg-gradient-to-br from-slate-950 to-sky-700 text-white shadow-[0_0_22px_rgba(14,165,233,0.22)]">
          <ShieldCheck size={20} />
        </div>
        <div>
          <div className="text-sm font-semibold tracking-wide text-ink">AeroAPI</div>
          <div className="text-xs text-slate-500">AI API testing</div>
        </div>
      </div>
      <nav className="space-y-1 px-3 py-4">
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition duration-200 ${
                active ? "bg-slate-950 text-white shadow-[0_0_18px_rgba(14,165,233,0.18)]" : "text-slate-700 hover:-translate-y-0.5 hover:bg-sky-50 hover:text-sky-900"
              }`}
            >
              <Icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
