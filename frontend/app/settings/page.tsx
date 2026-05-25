"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Save } from "lucide-react";

type Settings = {
  provider: string;
  model: string;
  slackWebhook: string;
  intensity: string;
  timeout: number;
  concurrency: number;
};

const defaultSettings: Settings = {
  provider: "gemini",
  model: "gemini-1.5-flash",
  slackWebhook: "",
  intensity: "standard",
  timeout: 20,
  concurrency: 6
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const raw = localStorage.getItem("aeroapi-settings");
    if (raw) setSettings(JSON.parse(raw));
  }, []);

  function save() {
    localStorage.setItem("aeroapi-settings", JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>
        <p className="mt-1 text-sm text-slate-600">Local UI defaults for new runs. Provider tokens are not saved.</p>
      </div>
      <section className="space-y-4 rounded border border-line bg-white p-5 shadow-soft">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Default provider">
            <select className="w-full rounded border border-line px-3 py-2 text-sm" value={settings.provider} onChange={(e) => setSettings({ ...settings, provider: e.target.value })}>
              <option value="gemini">Gemini</option>
              <option value="groq">Groq</option>
              <option value="claude">Claude</option>
              <option value="codex">Codex</option>
              <option value="openai-compatible">OpenAI-compatible</option>
              <option value="custom">Custom</option>
            </select>
          </Field>
          <Field label="Default model">
            <input className="w-full rounded border border-line px-3 py-2 text-sm" value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })} />
          </Field>
          <Field label="Slack webhook">
            <input className="w-full rounded border border-line px-3 py-2 text-sm" value={settings.slackWebhook} onChange={(e) => setSettings({ ...settings, slackWebhook: e.target.value })} />
          </Field>
          <Field label="Test intensity">
            <select className="w-full rounded border border-line px-3 py-2 text-sm" value={settings.intensity} onChange={(e) => setSettings({ ...settings, intensity: e.target.value })}>
              <option value="standard">Standard</option>
              <option value="deep">Deep</option>
            </select>
          </Field>
          <Field label="Timeout seconds">
            <input className="w-full rounded border border-line px-3 py-2 text-sm" type="number" min={1} max={120} value={settings.timeout} onChange={(e) => setSettings({ ...settings, timeout: Number(e.target.value) })} />
          </Field>
          <Field label="Concurrency">
            <input className="w-full rounded border border-line px-3 py-2 text-sm" type="number" min={1} max={25} value={settings.concurrency} onChange={(e) => setSettings({ ...settings, concurrency: Number(e.target.value) })} />
          </Field>
        </div>
        <button onClick={save} className="inline-flex items-center gap-2 rounded bg-ink px-4 py-2 text-sm font-medium text-white">
          <Save size={16} /> Save defaults
        </button>
        {saved && <span className="ml-3 text-sm text-emerald-700">Saved locally.</span>}
      </section>
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
