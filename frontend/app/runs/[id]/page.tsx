"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ChevronDown, Download, GitBranch, RefreshCcw, Send, StopCircle } from "lucide-react";
import { API_BASE, apiFetch, ResultRow, RunSummary } from "@/lib/api";
import { SeverityBadge, StatusBadge } from "@/components/badges";

const severities = ["all", "critical", "high", "medium", "low", "info"];

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<RunSummary | null>(null);
  const [results, setResults] = useState<ResultRow[]>([]);
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [open, setOpen] = useState<number | null>(null);
  const [slackWebhook, setSlackWebhook] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let source: EventSource | null = null;
    async function load() {
      const current = await apiFetch<RunSummary>(`/api/runs/${runId}`);
      setRun(current);
      if (current.status === "completed" || current.status === "failed" || current.status === "cancelled") {
        setResults(await apiFetch<ResultRow[]>(`/api/runs/${runId}/results`));
      }
    }
    load();
    source = new EventSource(`${API_BASE}/api/runs/${runId}/events`);
    source.addEventListener("progress", async (event) => {
      const current = JSON.parse((event as MessageEvent).data) as RunSummary;
      setRun(current);
      if (["completed", "failed", "cancelled"].includes(current.status)) {
        source?.close();
        setResults(await apiFetch<ResultRow[]>(`/api/runs/${runId}/results`));
      }
    });
    return () => source?.close();
  }, [runId]);

  const filtered = useMemo(() => {
    return results.filter((item) => {
      const matchesSeverity = severity === "all" || item.severity === severity;
      const haystack = `${item.endpoint.path} ${item.test_name} ${item.status}`.toLowerCase();
      return matchesSeverity && haystack.includes(query.toLowerCase());
    });
  }, [results, query, severity]);

  async function cancelRun() {
    const next = await apiFetch<RunSummary>(`/api/runs/${runId}/cancel`, { method: "POST" });
    setRun(next);
  }

  async function sendSlack() {
    if (!slackWebhook) return;
    await fetch(`${API_BASE}/api/runs/${runId}/slack?webhook_url=${encodeURIComponent(slackWebhook)}`, { method: "POST" });
    setMessage("Slack alert sent.");
  }

  if (!run) return <div className="text-sm text-slate-600">Loading run...</div>;

  const progress = run.total_tests ? Math.round((run.completed_tests / run.total_tests) * 100) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Run #{run.id}</h1>
          <p className="mt-1 text-sm text-slate-600">{run.stage}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => location.reload()} className="inline-flex items-center gap-2 rounded border border-line bg-white px-3 py-2 text-sm"><RefreshCcw size={16} /> Refresh</button>
          {!["completed", "failed", "cancelled"].includes(run.status) && (
            <button onClick={cancelRun} className="inline-flex items-center gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"><StopCircle size={16} /> Cancel</button>
          )}
        </div>
      </div>

      <section className="rounded border border-line bg-white p-4 shadow-soft">
        <div className="mb-3 flex items-center justify-between">
          <StatusBadge value={run.status} />
          <span className="text-sm text-slate-600">{run.completed_tests}/{run.total_tests} tests</span>
        </div>
        <div className="h-2 overflow-hidden rounded bg-slate-100">
          <div className="h-full bg-emerald-600 transition-all" style={{ width: `${progress}%` }} />
        </div>
        <div className="mt-4 grid grid-cols-5 gap-3 text-sm">
          <Metric label="Endpoints" value={run.total_endpoints} />
          <Metric label="Passed" value={run.passed_count} />
          <Metric label="Failed" value={run.failed_count} />
          <Metric label="Security" value={run.security_count} />
          <Metric label="Regressions" value={run.regression_count} />
        </div>
        {run.error_message && <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{run.error_message}</div>}
      </section>

      <section className="rounded border border-line bg-white shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            {severities.map((item) => (
              <button key={item} onClick={() => setSeverity(item)} className={`rounded px-3 py-1.5 text-xs font-medium ${severity === item ? "bg-ink text-white" : "bg-slate-100 text-slate-700"}`}>{item}</button>
            ))}
          </div>
          <input className="w-72 rounded border border-line px-3 py-2 text-sm" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search endpoint, test, status" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Endpoint</th>
                <th className="px-4 py-3">Test</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">HTTP</th>
                <th className="px-4 py-3">Latency</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td className="px-4 py-6 text-slate-500" colSpan={6}>Results appear after the run finishes.</td></tr>
              ) : filtered.map((item) => (
                <Fragment key={item.id}>
                  <tr onClick={() => setOpen(open === item.id ? null : item.id)} className={`cursor-pointer border-t border-line transition duration-150 hover:bg-panel ${hasDependencies(item) ? "bg-sky-50/60" : ""} ${dependencyFailed(item) ? "border-l-4 border-l-red-400" : ""}`}>
                    <td className="px-4 py-3 font-mono text-xs">{item.endpoint.method} {item.endpoint.path}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {hasDependencies(item) && <GitBranch size={15} className="text-sky-700" />}
                        <span>{item.test_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3"><SeverityBadge value={item.severity} /></td>
                    <td className="px-4 py-3"><StatusBadge value={item.status} /></td>
                    <td className="px-4 py-3">{item.response_status ?? "-"}</td>
                    <td className="px-4 py-3">{item.latency_ms}ms</td>
                  </tr>
                  {open === item.id && (
                    <tr className="border-t border-line bg-slate-50">
                      <td colSpan={6} className="px-4 py-4">
                        {hasDependencies(item) && <DependencyFlow request={item.request} />}
                        <div className="grid grid-cols-2 gap-4">
                          <Inspector title="Main request" value={mainRequest(item.request)} />
                          <Inspector title="Response" value={{ status: item.response_status, headers: item.response_headers, body: item.response_body_preview }} />
                        </div>
                        <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
                          <Info title="Finding" value={item.finding_summary} />
                          <Info title="Suggested fix" value={item.suggested_fix} />
                          <Info title="AI reasoning" value={item.ai_reasoning} />
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-3 rounded border border-line bg-white p-4 shadow-soft">
        <a href={`${API_BASE}/api/runs/${runId}/export/html`} className="inline-flex items-center gap-2 rounded bg-ink px-3 py-2 text-sm font-medium text-white"><Download size={16} /> HTML</a>
        <a href={`${API_BASE}/api/runs/${runId}/export/csv`} className="inline-flex items-center gap-2 rounded border border-line px-3 py-2 text-sm"><Download size={16} /> CSV</a>
        <a href={`${API_BASE}/api/runs/${runId}/export/postman`} className="inline-flex items-center gap-2 rounded border border-line px-3 py-2 text-sm"><Download size={16} /> Postman collection</a>
        <input className="min-w-80 rounded border border-line px-3 py-2 text-sm" value={slackWebhook} onChange={(e) => setSlackWebhook(e.target.value)} placeholder="Slack webhook URL" />
        <button onClick={sendSlack} className="inline-flex items-center gap-2 rounded border border-line px-3 py-2 text-sm"><Send size={16} /> Send Slack alert</button>
        {message && <span className="text-sm text-emerald-700">{message}</span>}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded border border-line bg-panel p-3"><div className="text-lg font-semibold text-ink">{value}</div><div className="text-xs text-slate-500">{label}</div></div>;
}

function Inspector({ title, value }: { title: string; value: unknown }) {
  return <div><div className="mb-2 text-xs font-semibold uppercase text-slate-500">{title}</div><pre className="max-h-80 overflow-auto rounded bg-ink p-3 text-xs text-slate-100">{JSON.stringify(value, null, 2)}</pre></div>;
}

function Info({ title, value }: { title: string; value: string }) {
  return <div className="rounded border border-line bg-white p-3"><div className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</div><p className="text-sm text-slate-700">{value}</p></div>;
}

function hasDependencies(item: ResultRow) {
  const dependencies = item.request.dependencies as { before?: unknown[]; after?: unknown[] } | undefined;
  return Boolean((dependencies?.before?.length ?? 0) + (dependencies?.after?.length ?? 0));
}

function dependencyFailed(item: ResultRow) {
  const dependencies = item.request.dependencies as { before?: DependencyStep[]; after?: DependencyStep[] } | undefined;
  return [...(dependencies?.before ?? []), ...(dependencies?.after ?? [])].some((step) => Boolean(step.error) || Number(step.status ?? 0) >= 400);
}

function mainRequest(request: Record<string, unknown>) {
  return request.main ?? request;
}

function DependencyFlow({ request }: { request: Record<string, unknown> }) {
  const dependencies = request.dependencies as { before?: DependencyStep[]; after?: DependencyStep[] } | undefined;
  const before = dependencies?.before ?? [];
  const after = dependencies?.after ?? [];
  return (
    <div className="mb-4 rounded border border-sky-200 bg-white p-3 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-sky-900">
        <GitBranch size={16} />
        Dependency flow
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <StepGroup title="Before main request" steps={before} tone="sky" />
        <StepGroup title="Main request" steps={[mainStep(request)]} tone="emerald" />
        <StepGroup title="After main request" steps={after} tone="amber" />
      </div>
    </div>
  );
}

type DependencyStep = {
  name?: string;
  method?: string;
  url?: string;
  status?: number | null;
  error?: string;
  extracts?: Record<string, string>;
  request?: unknown;
  response?: unknown;
};

function mainStep(request: Record<string, unknown>): DependencyStep {
  const main = mainRequest(request) as Record<string, unknown>;
  return { name: "Main API test", method: String(main.method ?? ""), url: String(main.url ?? ""), request: main };
}

function StepGroup({ title, steps, tone }: { title: string; steps: DependencyStep[]; tone: "sky" | "emerald" | "amber" }) {
  const [openStep, setOpenStep] = useState<number | null>(null);
  const toneClass = {
    sky: "border-sky-200 bg-sky-50 text-sky-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-950",
    amber: "border-amber-200 bg-amber-50 text-amber-950"
  }[tone];
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase text-slate-500">{title}</div>
      <div className="space-y-2">
        {steps.length === 0 ? (
          <div className="rounded border border-line bg-panel p-2 text-xs text-slate-500">No steps</div>
        ) : steps.map((step, index) => {
          const selected = openStep === index;
          return (
            <div key={`${step.name}-${index}`} className={`rounded border text-xs ${toneClass} ${selected ? "ring-2 ring-slate-900/10" : ""}`}>
              <button
                type="button"
                onClick={() => setOpenStep(selected ? null : index)}
                className="flex w-full items-start justify-between gap-2 p-2 text-left transition duration-150 hover:bg-white/40"
              >
                <span className="min-w-0">
                  <span className="block font-semibold">{step.method} {step.name}</span>
                  <span className="mt-1 block break-all font-mono text-[11px]">{step.url}</span>
                  {"status" in step && <span className="mt-1 block">Status: {step.status ?? step.error ?? "-"}</span>}
                  {step.extracts && Object.keys(step.extracts).length > 0 && <span className="mt-1 block">Extracts: {Object.keys(step.extracts).join(", ")}</span>}
                </span>
                <ChevronDown size={15} className={`mt-1 shrink-0 transition duration-200 ${selected ? "rotate-180" : ""}`} />
              </button>
              {selected && (
                <div className="border-t border-white/70 p-2">
                  <button
                    type="button"
                    onClick={() => setOpenStep(null)}
                    className="mb-2 rounded border border-white/70 bg-white/80 px-2 py-1 text-[11px] font-medium text-slate-700 transition hover:border-sky-300 hover:text-sky-700"
                  >
                    Hide details
                  </button>
                  <StepDebugPanel step={step} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StepDebugPanel({ step }: { step: DependencyStep }) {
  const response = step.response ?? { status: step.status ?? null, error: step.error ?? null };
  return (
    <div className="rounded border border-slate-200 bg-white p-2 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-ink">{step.method} {step.name}</div>
          <div className="mt-1 break-all font-mono text-[11px] text-slate-500">{step.url}</div>
        </div>
        {"status" in step && <StatusChip status={step.status} error={step.error} />}
      </div>
      <div className="grid gap-2">
        <DebugInspector title="Request" value={step.request ?? step} />
        <DebugInspector title="Response" value={response} />
      </div>
    </div>
  );
}

function StatusChip({ status, error }: { status?: number | null; error?: string }) {
  const isError = Boolean(error) || Number(status ?? 0) >= 400;
  const label = status ?? error ?? "-";
  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isError ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}>Status {label}</span>;
}

function DebugInspector({ title, value }: { title: string; value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  return (
    <div className="min-w-0 rounded border border-line bg-slate-50">
      <div className="flex items-center justify-between border-b border-line px-2 py-1.5">
        <div className="text-xs font-semibold uppercase text-slate-500">{title}</div>
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(text)}
          className="rounded border border-line bg-white px-2 py-1 text-[11px] font-medium text-slate-600 transition hover:border-sky-300 hover:text-sky-700"
        >
          Copy
        </button>
      </div>
      <pre className="max-h-96 min-h-36 overflow-auto p-2 text-[11px] leading-relaxed text-slate-100">
        <code className="block rounded bg-slate-950 p-2">{text}</code>
      </pre>
    </div>
  );
}

function MiniInspector({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase text-slate-500">{title}</div>
      <pre className="max-h-72 overflow-auto rounded bg-slate-950 p-2 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
