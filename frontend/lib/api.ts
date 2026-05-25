export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type RunSummary = {
  id: number;
  status: string;
  stage: string;
  provider: string;
  model: string;
  total_endpoints: number;
  total_tests: number;
  completed_tests: number;
  passed_count: number;
  failed_count: number;
  security_count: number;
  regression_count: number;
  error_message?: string | null;
};

export type ResultRow = {
  id: number;
  endpoint: {
    id: number;
    name: string;
    method: string;
    path: string;
    url: string;
    auth_type: string;
  };
  test_name: string;
  category: string;
  severity: string;
  status: string;
  request: Record<string, unknown>;
  response_status: number | null;
  response_headers: Record<string, unknown>;
  response_body_preview: string;
  latency_ms: number;
  finding_summary: string;
  suggested_fix: string;
  ai_reasoning: string;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {})
      },
      cache: "no-store"
    });
  } catch {
    throw new Error(`Could not reach the backend at ${API_BASE}. Make sure the backend server is running and CORS allows this frontend port.`);
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}
