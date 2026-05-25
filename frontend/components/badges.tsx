const severityClasses: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
  info: "bg-slate-100 text-slate-700 border-slate-200"
};

const statusClasses: Record<string, string> = {
  passed: "bg-emerald-100 text-emerald-800 border-emerald-200",
  failed: "bg-red-100 text-red-800 border-red-200",
  error: "bg-red-100 text-red-800 border-red-200",
  warning: "bg-amber-100 text-amber-800 border-amber-200",
  completed: "bg-emerald-100 text-emerald-800 border-emerald-200",
  running: "bg-blue-100 text-blue-800 border-blue-200",
  generating: "bg-cyan-100 text-cyan-800 border-cyan-200",
  pending: "bg-slate-100 text-slate-700 border-slate-200",
  cancelled: "bg-slate-100 text-slate-700 border-slate-200"
};

export function SeverityBadge({ value }: { value: string }) {
  return <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${severityClasses[value] ?? severityClasses.info}`}>{value}</span>;
}

export function StatusBadge({ value }: { value: string }) {
  return <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${statusClasses[value] ?? statusClasses.pending}`}>{value}</span>;
}
