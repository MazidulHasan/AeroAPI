"use client";

import { useState } from "react";
import { Activity, AlertTriangle } from "lucide-react";

export function Topbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-10 ml-64 flex h-16 items-center justify-between border-b border-line bg-white/95 px-6 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <Activity size={17} className="text-emerald-600" />
        Local runner ready
      </div>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="group flex h-9 w-9 items-center justify-center rounded-full border border-amber-300 bg-amber-50 text-amber-800 shadow-sm transition duration-200 hover:border-amber-400 hover:bg-amber-100 hover:shadow-[0_0_18px_rgba(245,158,11,0.28)]"
          aria-label="Show safety warning"
        >
          <AlertTriangle size={17} className="transition duration-200 group-hover:scale-110" />
        </button>
        {open && (
          <div className="absolute right-0 top-11 w-80 rounded border border-amber-200 bg-white p-3 text-sm text-amber-950 shadow-soft">
            Run only against APIs you own or have permission to test.
          </div>
        )}
      </div>
    </header>
  );
}
