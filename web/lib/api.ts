// Thin fetch client for the FastAPI bridge in ../api. Every function here
// is a 1:1 call to a real endpoint — no fabricated data, no client-side
// business logic. See api/main.py for the endpoint definitions.

import type {
  ApplicationsView,
  MissionControlView,
  OpportunitiesView,
  OpportunityDetail,
  ResumeStudioView,
  StrategyView,
  SystemView,
} from "./types";
import { ApiError, apiRequest } from "./api-config";

const SESSION_KEY = "hireloop_session_id";

// session_id identifies one workflow/job-search session (created by
// POST /api/session, held in-memory by api/engine.py's _SESSIONS map).
// This is NOT the same concept as owner_id (the persistent Career
// Profile identity used by lib/career-profile-api.ts) -- a session_id
// is disposable and workflow-scoped, an owner_id is durable and
// person-scoped. Never pass one where the other is expected.
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  return apiRequest<T>(path, init);
}

export function getStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SESSION_KEY);
}

export async function ensureSession(): Promise<string> {
  const existing = getStoredSessionId();
  if (existing) return existing;
  const { session_id } = await req<{ session_id: string }>("/api/session", { method: "POST" });
  window.localStorage.setItem(SESSION_KEY, session_id);
  return session_id;
}

export function resetSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_KEY);
}

// ---------------------------------------------------------------------------
// Stale-session recovery (Priority 1, Part 48/44 hardening pass)
//
// session_id lives only in api/engine.py's in-memory _SESSIONS map -- it
// disappears on any FastAPI process restart, while the Career Profile
// (owner_id, SQLite-backed) survives. When that happens, every workflow /
// Mission-Control / Discovery / Opportunity call gets back exactly
// `404 {"detail": "Unknown session_id. POST /api/session first."}` from
// api/main.py's `_sess()` helper. That message is specific and distinct
// from a genuine "unknown job_id" 404 (a different detail string, see
// api/main.py's opportunity_detail endpoint) -- ONLY this exact case
// triggers recovery.
//
// Recovery here is: drop the stale session_id (never touch owner_id or
// any Career Profile state), mint a fresh session_id, and retry the
// ORIGINAL failed request exactly once against the new session_id. It
// never re-runs discovery, auto-selects an opportunity, or auto-starts
// the demo -- those all require an explicit user action, unaffected by
// this recovery path. If recovery itself fails (backend still
// unreachable, etc.), a SessionRecoveryFailedError is thrown so the UI
// can show a controlled "Your search session expired. Your Career
// Profile is safe." message instead of a raw 404.
function isStaleSessionError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 404 && /unknown session_id/i.test(e.detail);
}

export class SessionRecoveryFailedError extends Error {
  constructor() {
    super("Your search session expired. Your Career Profile is safe.");
  }
}

type SessionRecoveredListener = (newSessionId: string) => void;
const recoveryListeners = new Set<SessionRecoveredListener>();

/** Subscribe to be told when a stale session_id was silently swapped for a
 * fresh one, so UI state (e.g. SessionProvider's sessionId) can follow. */
export function onSessionRecovered(listener: SessionRecoveredListener): () => void {
  recoveryListeners.add(listener);
  return () => recoveryListeners.delete(listener);
}

let recoveryInFlight: Promise<string> | null = null;

async function recoverSession(): Promise<string> {
  // Dedupe concurrent recoveries (e.g. several views hitting a stale
  // session_id at once) into a single POST /api/session call, and bound
  // retries to exactly one attempt per failed request -- no loops.
  if (!recoveryInFlight) {
    recoveryInFlight = (async () => {
      resetSession();
      try {
        const { session_id } = await apiRequest<{ session_id: string }>("/api/session", { method: "POST" });
        window.localStorage.setItem(SESSION_KEY, session_id);
        for (const listener of recoveryListeners) listener(session_id);
        return session_id;
      } catch {
        throw new SessionRecoveryFailedError();
      }
    })();
  }
  try {
    return await recoveryInFlight;
  } finally {
    recoveryInFlight = null;
  }
}

/** Every session-scoped request goes through here instead of calling
 * apiRequest directly, so stale-session recovery is centralized in one
 * place rather than copy-pasted per page/call site. */
async function sessionReq<T>(buildPath: (sid: string) => string, sid: string, init?: RequestInit): Promise<T> {
  try {
    return await apiRequest<T>(buildPath(sid), init);
  } catch (e) {
    if (!isStaleSessionError(e)) throw e;
    const freshSid = await recoverSession(); // throws SessionRecoveryFailedError on failure
    return await apiRequest<T>(buildPath(freshSid), init); // single bounded retry
  }
}

export const api = {
  missionControl: (sid: string) => sessionReq<MissionControlView>((s) => `/api/session/${s}/mission-control`, sid),
  opportunities: (sid: string) => sessionReq<OpportunitiesView>((s) => `/api/session/${s}/opportunities`, sid),
  opportunityDetail: (sid: string, jobId: string) =>
    sessionReq<OpportunityDetail>((s) => `/api/session/${s}/opportunities/${jobId}`, sid),
  resumeStudio: (sid: string) => sessionReq<ResumeStudioView>((s) => `/api/session/${s}/resume-studio`, sid),
  applications: (sid: string) => sessionReq<ApplicationsView>((s) => `/api/session/${s}/applications`, sid),
  strategy: (sid: string) => sessionReq<StrategyView>((s) => `/api/session/${s}/strategy`, sid),
  system: (sid: string) => sessionReq<SystemView>((s) => `/api/session/${s}/system`, sid),

  demoStart: (sid: string) =>
    sessionReq<MissionControlView>((s) => `/api/session/${s}/demo/start`, sid, { method: "POST" }),

  run: (sid: string, body: { resume_path?: string; target_roles: string[]; work_modes: string[]; owner_id?: string }) =>
    sessionReq<MissionControlView>((s) => `/api/session/${s}/run`, sid, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  resume: (
    sid: string,
    body: { action: string; job_id?: string; modification_ids?: string[]; confirmation_detail?: string }
  ) =>
    sessionReq<MissionControlView>((s) => `/api/session/${s}/resume`, sid, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  outcomeStart: (sid: string, applicationId: string) =>
    sessionReq((s) => `/api/session/${s}/applications/${applicationId}/outcome/start`, sid, { method: "POST" }),

  outcomeSubmit: (sid: string, applicationId: string, body: { action: string; confirm?: boolean }) =>
    sessionReq((s) => `/api/session/${s}/applications/${applicationId}/outcome/submit`, sid, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
