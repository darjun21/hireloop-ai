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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SESSION_KEY = "hireloop_session_id";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
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

export const api = {
  missionControl: (sid: string) => req<MissionControlView>(`/api/session/${sid}/mission-control`),
  opportunities: (sid: string) => req<OpportunitiesView>(`/api/session/${sid}/opportunities`),
  opportunityDetail: (sid: string, jobId: string) =>
    req<OpportunityDetail>(`/api/session/${sid}/opportunities/${jobId}`),
  resumeStudio: (sid: string) => req<ResumeStudioView>(`/api/session/${sid}/resume-studio`),
  applications: (sid: string) => req<ApplicationsView>(`/api/session/${sid}/applications`),
  strategy: (sid: string) => req<StrategyView>(`/api/session/${sid}/strategy`),
  system: (sid: string) => req<SystemView>(`/api/session/${sid}/system`),

  demoStart: (sid: string) =>
    req<MissionControlView>(`/api/session/${sid}/demo/start`, { method: "POST" }),

  run: (sid: string, body: { resume_path?: string; target_roles: string[]; work_modes: string[] }) =>
    req<MissionControlView>(`/api/session/${sid}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  resume: (
    sid: string,
    body: { action: string; job_id?: string; modification_ids?: string[]; confirmation_detail?: string }
  ) =>
    req<MissionControlView>(`/api/session/${sid}/resume`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  outcomeStart: (sid: string, applicationId: string) =>
    req(`/api/session/${sid}/applications/${applicationId}/outcome/start`, { method: "POST" }),

  outcomeSubmit: (sid: string, applicationId: string, body: { action: string; confirm?: boolean }) =>
    req(`/api/session/${sid}/applications/${applicationId}/outcome/submit`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
