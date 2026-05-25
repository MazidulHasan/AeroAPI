"use client";

import { ChangeEvent, DragEvent, FormEvent, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, FileJson, KeyRound, Play, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";

const providerModels: Record<string, string[]> = {
  gemini: ["gemini-1.5-flash", "gemini-1.5-pro"],
  groq: ["qwen/qwen3-32b", "mixtral-8x7b-32768"],
  claude: ["claude-3-5-sonnet-latest", "claude-3-haiku"],
  codex: ["openai-compatible-codex"],
  "openai-compatible": ["gpt-4o-mini", "gpt-4.1-mini"],
  custom: ["custom-model"]
};

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
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState(providerModels.gemini[0]);
  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [intensity, setIntensity] = useState("standard");
  const [timeout, setTimeoutValue] = useState(20);
  const [concurrency, setConcurrency] = useState(6);
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
        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
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

          {uploadPreview && (
            <div className="rounded border border-line bg-panel p-3 text-sm">
              Parsed {uploadPreview.endpoint_count} endpoint(s) from {uploadPreview.name}.
            </div>
          )}
        </section>

        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
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
        </section>

        <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
          <h2 className="text-sm font-semibold text-ink">Execution</h2>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Base URL override">
              <input className="w-full rounded border border-line px-3 py-2 text-sm" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.yourdomain.com" />
            </Field>
            <Field label="Slack webhook">
              <input className="w-full rounded border border-line px-3 py-2 text-sm" value={slackWebhook} onChange={(e) => setSlackWebhook(e.target.value)} placeholder="Optional" />
            </Field>
            <Field label="Test intensity">
              <select className="w-full rounded border border-line px-3 py-2 text-sm" value={intensity} onChange={(e) => setIntensity(e.target.value)}>
                <option value="standard">Standard</option>
                <option value="deep">Deep</option>
              </select>
            </Field>
            <Field label="Timeout seconds">
              <input className="w-full rounded border border-line px-3 py-2 text-sm" type="number" min={1} max={120} value={timeout} onChange={(e) => setTimeoutValue(Number(e.target.value))} />
            </Field>
            <Field label="Concurrency">
              <input className="w-full rounded border border-line px-3 py-2 text-sm" type="number" min={1} max={25} value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} />
            </Field>
          </div>
        </section>

        <aside className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
          <div className="flex gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle size={18} className="shrink-0" />
            Security probes should run only against authorized systems. Deep mode adds stronger mutation checks.
          </div>
          {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
          <button disabled={submitting} className="inline-flex w-full items-center justify-center gap-2 rounded bg-ink px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60">
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
