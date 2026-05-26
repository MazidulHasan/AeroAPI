import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight, Bug, CheckCircle2, FileText, ShieldAlert } from "lucide-react";
import { apiFetch, RunSummary } from "@/lib/api";
import { StatusBadge } from "@/components/badges";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let runs: RunSummary[] = [];
  try {
    runs = await apiFetch<RunSummary[]>("/api/runs");
  } catch {
    runs = [];
  }
  const latest = runs[0];
  const totals = runs.reduce(
    (acc, run) => ({
      passed: acc.passed + run.passed_count,
      failed: acc.failed + run.failed_count,
      security: acc.security + run.security_count,
      regressions: acc.regressions + run.regression_count
    }),
    { passed: 0, failed: 0, security: 0, regressions: 0 }
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-600">Recent API test activity and security signal.</p>
        </div>
        <Link href="/new-run" className="inline-flex items-center gap-2 rounded bg-gradient-to-r from-slate-950 to-sky-900 px-4 py-2 text-sm font-medium text-white transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(14,165,233,0.28)]">
          New run <ArrowUpRight size={16} />
        </Link>
      </div>

      <section className="grid grid-cols-4 gap-4">
        <Metric icon={<CheckCircle2 size={20} />} label="Passed" value={totals.passed} accent="text-emerald-700" />
        <Metric icon={<Bug size={20} />} label="Failed" value={totals.failed} accent="text-red-700" />
        <Metric icon={<ShieldAlert size={20} />} label="Security findings" value={totals.security} accent="text-orange-700" />
        <Metric icon={<FileText size={20} />} label="Regressions" value={totals.regressions} accent="text-blue-700" />
      </section>

      <section className="rounded border border-line bg-white shadow-soft">
        <div className="border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">Recent runs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Run</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Progress</th>
                <th className="px-4 py-3">Failed</th>
                <th className="px-4 py-3">Security</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr><td className="px-4 py-6 text-slate-500" colSpan={6}>No runs yet. Start with a Postman collection.</td></tr>
              ) : runs.map((run) => (
                <tr key={run.id} className="border-t border-line transition duration-150 hover:bg-sky-50/70">
                  <td className="px-4 py-3"><Link href={`/runs/${run.id}`} className="font-medium text-ink hover:underline">#{run.id}</Link></td>
                  <td className="px-4 py-3">{run.provider} / {run.model}</td>
                  <td className="px-4 py-3"><StatusBadge value={run.status} /></td>
                  <td className="px-4 py-3">{run.completed_tests}/{run.total_tests}</td>
                  <td className="px-4 py-3">{run.failed_count}</td>
                  <td className="px-4 py-3">{run.security_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {latest && (
        <section className="rounded border border-line bg-white p-4 shadow-soft transition duration-200 hover:border-sky-200 hover:shadow-[0_14px_32px_rgba(14,165,233,0.12)]">
          <div className="text-sm font-semibold text-ink">Active context</div>
          <p className="mt-1 text-sm text-slate-600">Latest run #{latest.id} is {latest.stage} with {latest.total_endpoints} endpoint(s) discovered.</p>
        </section>
      )}
    </div>
  );
}

function Metric({ icon, label, value, accent }: { icon: ReactNode; label: string; value: number; accent: string }) {
  return (
    <div className="rounded border border-line bg-white p-4 shadow-soft transition duration-200 hover:-translate-y-1 hover:border-sky-200 hover:shadow-[0_16px_34px_rgba(14,165,233,0.14)]">
      <div className={`mb-3 transition duration-200 ${accent}`}>{icon}</div>
      <div className="text-2xl font-semibold text-ink">{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
    </div>
  );
}
