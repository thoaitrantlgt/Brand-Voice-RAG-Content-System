export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const ROOT_BASE = API_BASE.replace(/\/api\/v1\/?$/, "");

export type Job = {
  job_id: string;
  project_id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result?: Record<string, unknown> | null;
  error?: { message?: string } | null;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : detail?.error ?? `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function health() {
  const response = await fetch(`${ROOT_BASE}/health`, { cache: "no-store" });
  if (!response.ok) throw new Error("Backend unavailable");
  return response.json();
}

export async function waitForJob(jobId: string, timeoutMs = 240_000): Promise<Job> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const job = await api<Job>(`/jobs/${jobId}`);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new Error(job.error?.message ?? "Job failed");
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error("Job timed out. It remains queued and can be checked later.");
}
