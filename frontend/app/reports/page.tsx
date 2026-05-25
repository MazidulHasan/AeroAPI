import Link from "next/link";
import { apiFetch, RunSummary } from "@/lib/api";
import { StatusBadge } from "@/components/badges";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  let runs: RunSummary[] = [];
  try {
    runs = await apiFetch<RunSummary[]>("/api/runs");
  } catch {
    runs = [];
  }
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Reports</h1>
        <p className="mt-1 text-sm text-slate-600">Historical runs, exports, and regression context.</p>
      </div>
      <section className="rounded border border-line bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Run</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Tests</th>
                <th className="px-4 py-3">Failed</th>
                <th className="px-4 py-3">Security</th>
                <th className="px-4 py-3">Regressions</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr><td className="px-4 py-6 text-slate-500" colSpan={7}>No reports yet.</td></tr>
              ) : runs.map((run) => (
                <tr key={run.id} className="border-t border-line">
                  <td className="px-4 py-3"><Link className="font-medium text-ink hover:underline" href={`/runs/${run.id}`}>Run #{run.id}</Link></td>
                  <td className="px-4 py-3"><StatusBadge value={run.status} /></td>
                  <td className="px-4 py-3">{run.provider}</td>
                  <td className="px-4 py-3">{run.completed_tests}/{run.total_tests}</td>
                  <td className="px-4 py-3">{run.failed_count}</td>
                  <td className="px-4 py-3">{run.security_count}</td>
                  <td className="px-4 py-3">{run.regression_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
