"use client";

import { Activity, AlertTriangle } from "lucide-react";

export function Topbar() {
  return (
    <header className="sticky top-0 z-10 ml-64 flex h-16 items-center justify-between border-b border-line bg-white/95 px-6 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <Activity size={17} className="text-emerald-600" />
        Local runner ready
      </div>
      <div className="flex items-center gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-800">
        <AlertTriangle size={15} />
        Run only against APIs you own or have permission to test
      </div>
    </header>
  );
}
