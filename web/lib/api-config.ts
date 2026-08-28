// Single source of truth for the FastAPI bridge's base URL and for how a
// failed request is turned into a structured, user-safe error. Every
// client module (lib/api.ts, lib/career-profile-api.ts) imports from
// here instead of independently reading process.env.NEXT_PUBLIC_API_BASE
// or hardcoding its own localhost fallback -- a real bug from a prior
// round was exactly that kind of drift (one file defaulting to
// "http://localhost:8000" while web/.env.local was set to
// "http://127.0.0.1:8000", which is a different CORS origin).

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

// Distinguishes *why* a request failed so the UI can show a readable
// message instead of a raw fetch/Python error string.
export type ApiErrorKind = "network" | "not_found" | "conflict" | "validation" | "server" | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** Full technical detail -- safe to console.error in dev, never shown to the user directly. */
  readonly detail: string;

  constructor(kind: ApiErrorKind, status: number | null, detail: string, userMessage: string) {
    super(userMessage);
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status >= 500) return "server";
  return "unknown";
}

function userMessageFor(kind: ApiErrorKind, status: number | null, detail: string): string {
  switch (kind) {
    case "network":
      return "CAREER PROFILE SERVICE UNAVAILABLE — We couldn't reach HireLoop's backend. Check that the API bridge is running and try again.";
    case "not_found":
      return "That item couldn't be found. It may have been removed or the session may have expired.";
    case "conflict":
      return "This change conflicts with something that already happened (e.g. an upload that was already applied). Please refresh and try again.";
    case "validation":
      // FastAPI 422 bodies are JSON like {"detail": "..."} or a Pydantic
      // error list. Prefer a short, readable string over raw Python/
      // Pydantic error text when we can extract one.
      return readableValidationMessage(detail);
    case "server":
      return "Something went wrong on HireLoop's backend. This has been logged — please try again in a moment.";
    default:
      return status ? `Request failed (${status}). Please try again.` : "Request failed. Please try again.";
  }
}

function readableValidationMessage(detail: string): string {
  const lower = detail.toLowerCase();
  if (lower.includes("work mode") || lower.includes("work_mode") || lower.includes("work_arrangements")) {
    return "Please select a supported work arrangement (Remote, Hybrid, Onsite, or Flexible).";
  }
  if (lower.includes("could not extract text") || lower.includes("unsupported file type") || lower.includes("empty file")) {
    return "That resume file couldn't be read. Please upload a PDF, DOCX, or TXT file under the size limit.";
  }
  return "Some of the information provided isn't valid. Please check the highlighted fields and try again.";
}

/**
 * Shared fetch wrapper. Turns a network failure (backend unreachable,
 * DNS error, CORS rejection surfaced as a TypeError by the browser) and
 * every non-2xx HTTP response into a structured ApiError instead of
 * letting a raw "Failed to fetch" TypeError propagate as an unhandled
 * rejection (which is what crashed the Career Profile page into Next.js's
 * runtime error overlay).
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch (err) {
    // fetch() throws a plain TypeError for network failures (backend
    // down, DNS failure, CORS preflight rejection, etc.) -- there is no
    // HTTP status in this case at all.
    const detail = err instanceof Error ? err.message : String(err);
    console.error(`[HireLoop API] network error calling ${path}:`, detail);
    throw new ApiError("network", null, detail, userMessageFor("network", null, detail));
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const kind = kindForStatus(res.status);
    console.error(`[HireLoop API] ${path} failed: ${res.status} ${text}`);
    throw new ApiError(kind, res.status, text, userMessageFor(kind, res.status, text));
  }

  return res.json() as Promise<T>;
}
