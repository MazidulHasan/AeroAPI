"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronDown, FileJson, FileText, KeyRound, Play, SlidersHorizontal, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";

const providerModels: Record<string, string[]> = {
  gemini: ["gemini-1.5-flash", "gemini-1.5-pro"],
  groq: ["qwen/qwen3-32b", "mixtral-8x7b-32768"],
  claude: ["claude-3-5-sonnet-latest", "claude-3-haiku"],
  codex: ["openai-compatible-codex"],
  "openai-compatible": ["gpt-4o-mini", "gpt-4.1-mini"],
  custom: ["custom-model"]
};

const savedRunInfoKey = "aeroapi.newRun.savedInfo";

type UploadResponse = {
  collection_id: number;
  name: string;
  endpoint_count: number;
  endpoints: Array<{ name: string; method: string; path: string }>;
};

export default function NewRunPage() {
  const router = useRouter();
  const [collectionFile, setCollectionFile] = useState<File | null>(null);
  const [envFile, setEnvFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [apiDocs, setApiDocs] = useState("");
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState(providerModels.gemini[0]);
  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [intensity, setIntensity] = useState("standard");
  const [timeout, setTimeoutValue] = useState(20);
  const [concurrency, setConcurrency] = useState(2);
  const [executionOpen, setExecutionOpen] = useState(false);
  const [autoSaveInfo, setAutoSaveInfo] = useState(false);
  const [warningOpen, setWarningOpen] = useState(false);
  const [uploadPreview, setUploadPreview] = useState<UploadResponse | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const models = useMemo(() => providerModels[provider] ?? ["default"], [provider]);
  const collectionStateClass = collectionFile
    ? "border-emerald-400 bg-emerald-50 text-emerald-950 hover:border-emerald-500"
    : "border-slate-300 bg-panel hover:border-slate-500";
  const environmentStateClass = envFile
    ? "border-emerald-400 bg-emerald-50 text-emerald-950"
    : "border-line bg-white text-slate-700";
  const docsStateClass = docFile || apiDocs.trim()
    ? "border-emerald-400 bg-emerald-50 text-emerald-950"
    : "border-line bg-white text-slate-700";

  useEffect(() => {
    const saved = localStorage.getItem(savedRunInfoKey);
    if (!saved) return;
    try {
      const parsed = JSON.parse(saved) as Partial<SavedRunInfo>;
      if (parsed.provider && providerModels[parsed.provider]) setProvider(parsed.provider);
      if (parsed.model) setModel(parsed.model);
      if (parsed.token) setToken(parsed.token);
      if (parsed.baseUrl) setBaseUrl(parsed.baseUrl);
      if (parsed.slackWebhook) setSlackWebhook(parsed.slackWebhook);
      if (parsed.customBaseUrl) setCustomBaseUrl(parsed.customBaseUrl);
      if (parsed.intensity) setIntensity(parsed.intensity);
      if (parsed.timeout) setTimeoutValue(parsed.timeout);
      if (parsed.concurrency) setConcurrency(parsed.concurrency);
      if (parsed.apiDocs) setApiDocs(parsed.apiDocs);
      setAutoSaveInfo(true);
    } catch {
      localStorage.removeItem(savedRunInfoKey);
    }
  }, []);

  useEffect(() => {
    if (!autoSaveInfo) return;
    localStorage.setItem(
      savedRunInfoKey,
      JSON.stringify({
        provider,
        model,
        token,
        baseUrl,
        slackWebhook,
        customBaseUrl,
        intensity,
        timeout,
        concurrency,
        apiDocs
      } satisfies SavedRunInfo)
    );
  }, [apiDocs, autoSaveInfo, baseUrl, concurrency, customBaseUrl, intensity, model, provider, slackWebhook, timeout, token]);

  function setCollection(file: File | null) {
    setCollectionFile(file);
    setUploadPreview(null);
    if (file) setError("");
  }

  function selectCollection(event: ChangeEvent<HTMLInputElement>) {
    setCollection(event.currentTarget.files?.[0] ?? null);
  }

  function selectEnvironment(event: ChangeEvent<HTMLInputElement>) {
    setEnvFile(event.currentTarget.files?.[0] ?? null);
  }

  async function selectDocs(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null;
    setDocFile(file);
    if (file) {
      setApiDocs(await file.text());
      setError("");
    }
  }

  function dropCollection(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setCollection(event.dataTransfer.files?.[0] ?? null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!collectionFile) {
      setError("Upload a Postman collection JSON file.");
      return;
    }
    if (!token.trim()) {
      setError("Enter an API token. It is sent only for this run and is not stored.");
      return;
    }
    setSubmitting(true);
    try {
      if (autoSaveInfo) {
        localStorage.setItem(
          savedRunInfoKey,
          JSON.stringify({
            provider,
            model,
            token,
            baseUrl,
            slackWebhook,
            customBaseUrl,
            intensity,
            timeout,
            concurrency,
            apiDocs
          } satisfies SavedRunInfo)
        );
      } else {
        localStorage.removeItem(savedRunInfoKey);
      }
      const form = new FormData();
      form.append("collection_file", collectionFile);
      if (envFile) form.append("env_file", envFile);
      const upload = await apiFetch<UploadResponse>("/api/collections/upload", { method: "POST", body: form });
      setUploadPreview(upload);
      const run = await apiFetch<{ id: number }>("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          collection_id: upload.collection_id,
          provider,
          model,
          api_token: token,
          api_docs: apiDocs.trim() || null,
          base_url_override: baseUrl || null,
          slack_webhook: slackWebhook || null,
          custom_base_url: customBaseUrl || null,
          test_intensity: intensity,
          timeout_seconds: timeout,
          concurrency
        })
      });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">New Run</h1>
        <p className="mt-1 text-sm text-slate-600">Upload a collection, choose a model, and launch generated API checks.</p>
      </div>

      <form onSubmit={submit} className="grid grid-cols-[1.25fr_0.75fr] gap-6">
        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-[0_14px_32px_rgba(14,165,233,0.12)]">
          <h2 className="text-sm font-semibold text-ink">Collection</h2>
          <label
            className={`flex min-h-40 cursor-pointer flex-col items-center justify-center rounded border border-dashed px-4 py-6 text-center ${collectionStateClass}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={dropCollection}
          >
            {collectionFile ? <CheckCircle2 className="mb-3 text-emerald-600" size={28} /> : <Upload className="mb-3 text-slate-500" size={28} />}
            <span className="text-sm font-medium text-ink">{collectionFile ? collectionFile.name : "Drop in your Postman collection"}</span>
            <span className={`mt-1 text-xs ${collectionFile ? "text-emerald-700" : "text-slate-500"}`}>{collectionFile ? "Collection selected" : "Click to choose a JSON collection or drop it here"}</span>
            <input className="sr-only" type="file" accept="application/json,.json" onChange={selectCollection} />
          </label>
          <label className={`flex items-center justify-between rounded border px-3 py-3 ${environmentStateClass}`}>
            <span className="flex min-w-0 items-center gap-2 text-sm">
              {envFile ? <CheckCircle2 size={17} className="shrink-0 text-emerald-600" /> : <FileJson size={17} className="shrink-0" />}
              <span className="truncate">{envFile ? envFile.name : "Environment JSON"}</span>
            </span>
            <input className="w-56 text-xs" type="file" accept="application/json,.json" onChange={selectEnvironment} />
          </label>
          <div className={`space-y-3 rounded border p-3 ${docsStateClass}`}>
            <div className="flex items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2 text-sm">
                {docFile || apiDocs.trim() ? <CheckCircle2 size={17} className="shrink-0 text-emerald-600" /> : <FileText size={17} className="shrink-0" />}
                <span className="truncate">{docFile ? docFile.name : "API docs or business rules"}</span>
              </span>
              <input className="w-56 text-xs" type="file" accept=".md,.txt,.json,.yaml,.yml,application/json,text/*" onChange={selectDocs} />
            </div>
            <textarea
              className="min-h-28 w-full rounded border border-line bg-white px-3 py-2 text-sm text-slate-800"
              value={apiDocs}
              onChange={(event) => {
                setApiDocs(event.target.value);
                setDocFile(null);
              }}
              placeholder="Paste endpoint docs, roles, workflows, validation rules, error contracts, or business constraints."
            />
          </div>

          {uploadPreview && (
            <div className="rounded border border-line bg-panel p-3 text-sm">
              Parsed {uploadPreview.endpoint_count} endpoint(s) from {uploadPreview.name}.
            </div>
          )}
        </section>

        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-[0_14px_32px_rgba(124,58,237,0.12)]">
          <h2 className="text-sm font-semibold text-ink">AI Provider</h2>
          <Field label="Provider">
            <select
              className="w-full rounded border border-line px-3 py-2 text-sm"
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value);
                setModel((providerModels[event.target.value] ?? ["default"])[0]);
              }}
            >
              <option value="gemini">Gemini</option>
              <option value="groq">Groq</option>
              <option value="claude">Claude</option>
              <option value="codex">Codex</option>
              <option value="openai-compatible">OpenAI-compatible</option>
              <option value="custom">Custom</option>
            </select>
          </Field>
          <Field label="Model">
            <input className="w-full rounded border border-line px-3 py-2 text-sm" list="models" value={model} onChange={(e) => setModel(e.target.value)} />
            <datalist id="models">{models.map((item) => <option key={item} value={item} />)}</datalist>
          </Field>
          {provider === "custom" && (
            <Field label="Custom base URL">
              <input className="w-full rounded border border-line px-3 py-2 text-sm" value={customBaseUrl} onChange={(e) => setCustomBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
            </Field>
          )}
          <Field label="API token">
            <div className="flex items-center gap-2 rounded border border-line px-3 py-2">
              <KeyRound size={16} className="text-slate-500" />
              <input className="w-full text-sm outline-none" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Stored only in job memory" />
            </div>
          </Field>
          <label className="flex items-start gap-2 rounded border border-line bg-panel p-3 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 rounded border-line text-sky-700"
              checked={autoSaveInfo}
              onChange={(event) => {
                setAutoSaveInfo(event.target.checked);
                if (!event.target.checked) localStorage.removeItem(savedRunInfoKey);
              }}
            />
            <span>
              <span className="block font-medium text-ink">Auto save for next run</span>
              <span className="mt-0.5 block text-xs text-slate-500">Saves provider, model, token, URLs, docs, and execution settings in this browser.</span>
            </span>
          </label>
        </section>

        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-[0_14px_32px_rgba(16,185,129,0.12)]">
          <button
            type="button"
            onClick={() => setExecutionOpen((value) => !value)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-ink">
              <SlidersHorizontal size={17} className="text-emerald-600" />
              Execution
            </span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-panel text-slate-700 transition duration-200 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700">
              <ChevronDown size={17} className={`transition duration-200 ${executionOpen ? "rotate-180" : ""}`} />
            </span>
          </button>
          <div className={`grid overflow-hidden transition-all duration-300 ease-out ${executionOpen ? "max-h-[520px] opacity-100" : "max-h-0 opacity-0"}`}>
            <div className="grid grid-cols-2 gap-4 pt-1">
              <Field label="Base URL override">
                <input className="w-full rounded border border-line px-3 py-2 text-sm transition focus:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-100" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.yourdomain.com" />
              </Field>
              <Field label="Slack webhook">
                <input className="w-full rounded border border-line px-3 py-2 text-sm transition focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-100" value={slackWebhook} onChange={(e) => setSlackWebhook(e.target.value)} placeholder="Optional" />
              </Field>
              <Field label="Test intensity">
                <select className="w-full rounded border border-line px-3 py-2 text-sm transition focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-100" value={intensity} onChange={(e) => setIntensity(e.target.value)}>
                  <option value="standard">Standard</option>
                  <option value="deep">Deep</option>
                </select>
              </Field>
              <Field label="Timeout seconds">
                <input className="w-full rounded border border-line px-3 py-2 text-sm transition focus:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-100" type="number" min={1} max={120} value={timeout} onChange={(e) => setTimeoutValue(Number(e.target.value))} />
              </Field>
              <Field label="Concurrency">
                <input className="w-full rounded border border-line px-3 py-2 text-sm transition focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100" type="number" min={1} max={25} value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} />
              </Field>
            </div>
          </div>
        </section>

        <aside className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
          <div className="relative flex justify-end">
            <button
              type="button"
              onClick={() => setWarningOpen((value) => !value)}
              className="group flex h-10 w-10 items-center justify-center rounded-full border border-amber-300 bg-amber-50 text-amber-800 transition duration-200 hover:border-amber-400 hover:bg-amber-100 hover:shadow-[0_0_22px_rgba(245,158,11,0.3)]"
              aria-label="Show security warning"
            >
              <AlertTriangle size={18} className="transition duration-200 group-hover:scale-110" />
            </button>
            {warningOpen && (
              <div className="absolute right-0 top-12 z-10 w-80 rounded border border-amber-200 bg-white p-3 text-sm text-amber-950 shadow-soft">
                Security probes should run only against authorized systems. Deep mode adds stronger mutation checks.
              </div>
            )}
          </div>
          {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
          <button disabled={submitting} className="inline-flex w-full items-center justify-center gap-2 rounded bg-gradient-to-r from-slate-950 to-sky-900 px-4 py-2.5 text-sm font-medium text-white transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(14,165,233,0.28)] disabled:cursor-not-allowed disabled:opacity-60">
            <Play size={17} />
            {submitting ? "Starting..." : "Run tests"}
          </button>
        </aside>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase text-slate-500">{label}</span>
      {children}
    </label>
  );
}

type SavedRunInfo = {
  provider: string;
  model: string;
  token: string;
  baseUrl: string;
  slackWebhook: string;
  customBaseUrl: string;
  intensity: string;
  timeout: number;
  concurrency: number;
  apiDocs: string;
};
