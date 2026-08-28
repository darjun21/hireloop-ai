// Thin fetch client for the /api/career-profile/* endpoints (api/career_profile_routes.py).
// Every function is a 1:1 call to a real endpoint -- no client-side fabrication.

import type {
  CareerProfile,
  ProfileCompleteness,
  ResumeUploadResponse,
  SessionMode,
} from "./career-profile-types";
import { apiRequest } from "./api-config";
import { sessionReq } from "./api";

const OWNER_ID_KEY = "hireloop_owner_id";

// This project has no authentication layer. owner_id identifies "this
// browser's real user" for the Career Profile feature -- generated once
// and persisted in localStorage, completely separate from the
// session_id used by the certification-demo/workflow session machinery
// in lib/session-context.tsx. A real multi-tenant auth layer is out of
// scope for this pass.
export function getOwnerId(): string {
  if (typeof window === "undefined") return "server";
  let ownerId = window.localStorage.getItem(OWNER_ID_KEY);
  if (!ownerId) {
    ownerId = `local-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    window.localStorage.setItem(OWNER_ID_KEY, ownerId);
  }
  return ownerId;
}

// owner_id (this module) identifies a persistent Career Profile -- it is
// NOT a session_id (lib/api.ts / lib/session-context.tsx), which
// identifies one disposable workflow/job-search session. See the note in
// getOwnerId() above and in lib/api.ts.
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  return apiRequest<T>(path, init);
}

export const careerProfileApi = {
  getOrCreate: (ownerId: string) => req<CareerProfile>(`/api/career-profile/${ownerId}`, { method: "POST" }),
  get: (ownerId: string) => req<CareerProfile>(`/api/career-profile/${ownerId}`),
  completeness: (ownerId: string) => req<ProfileCompleteness>(`/api/career-profile/${ownerId}/completeness`),

  updatePersonalInfo: (ownerId: string, body: Record<string, unknown>) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/personal-info`, { method: "PUT", body: JSON.stringify(body) }),

  updateWorkAuthorization: (ownerId: string, body: Record<string, unknown>) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/work-authorization`, { method: "PUT", body: JSON.stringify(body) }),

  updateTargetRoles: (ownerId: string, roles: { title: string; priority: string | null }[]) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/target-roles`, {
      method: "PUT",
      body: JSON.stringify({ roles }),
    }),

  updatePreferences: (ownerId: string, body: Record<string, unknown>) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/preferences`, { method: "PUT", body: JSON.stringify(body) }),

  updateApplicationAnswers: (ownerId: string, body: Record<string, unknown>) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/application-answers`, { method: "PUT", body: JSON.stringify(body) }),

  updateDemographics: (ownerId: string, body: Record<string, unknown>) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/demographics`, { method: "PUT", body: JSON.stringify(body) }),

  updateReferences: (ownerId: string, references: unknown[]) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/references`, { method: "PUT", body: JSON.stringify({ references }) }),

  uploadResume: (ownerId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<ResumeUploadResponse>(`/api/career-profile/${ownerId}/resume/upload`, { method: "POST", body: form });
  },

  applyResumeUpdate: (ownerId: string, uploadId: string) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/resume/apply`, {
      method: "POST",
      body: JSON.stringify({ upload_id: uploadId }),
    }),

  cancelResumeUpdate: (ownerId: string, uploadId: string) =>
    req<{ status: string }>(`/api/career-profile/${ownerId}/resume/cancel`, {
      method: "POST",
      body: JSON.stringify({ upload_id: uploadId }),
    }),

  // Field-level review/confirm actions -- resolve a flagged skill/work
  // experience/education/project entry without re-uploading a resume.
  // Pass an empty body ({}) to confirm an entry as-is; include fields to
  // correct them at the same time.
  reviewSkill: (ownerId: string, skillName: string, body: { name?: string } = {}) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/skills/${encodeURIComponent(skillName)}/review`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  reviewWorkExperience: (ownerId: string, entryId: string, body: Record<string, unknown> = {}) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/work-experience/${encodeURIComponent(entryId)}/review`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  reviewEducation: (ownerId: string, entryId: string, body: Record<string, unknown> = {}) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/education/${encodeURIComponent(entryId)}/review`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  reviewProject: (ownerId: string, entryId: string, body: Record<string, unknown> = {}) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/projects/${encodeURIComponent(entryId)}/review`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  confirmProfile: (ownerId: string) =>
    req<CareerProfile>(`/api/career-profile/${ownerId}/confirm`, { method: "POST" }),
};

// /api/session/{sid}/mode is a workflow-session-scoped route (like
// mission-control, opportunities, etc. in lib/api.ts), NOT an
// owner_id-scoped Career Profile route -- it must go through the exact
// same stale-session recovery as every other session-scoped call
// (lib/api.ts's sessionReq), never a bare apiRequest. Previously this
// used the unwrapped `req()` above, so a session_id that went stale
// between SessionProvider's initial read and this specific call (e.g.
// after a backend restart) produced an uncaught 404 here even when
// every other Mission Control call had already recovered successfully.
export async function fetchSessionMode(sessionId: string): Promise<SessionMode> {
  const res = await sessionReq<{ mode: SessionMode }>((sid) => `/api/session/${sid}/mode`, sessionId);
  return res.mode;
}
