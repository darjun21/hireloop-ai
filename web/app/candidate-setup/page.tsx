"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/lib/session-context";
import { careerProfileApi, getOwnerId } from "@/lib/career-profile-api";
import { api } from "@/lib/api";
import type { CareerProfile } from "@/lib/career-profile-types";
import type { SystemView } from "@/lib/types";

const ROLE_OPTIONS = ["AI Engineer", "Data Scientist", "ML Engineer", "Backend Engineer"];
const MODE_OPTIONS = ["Remote", "Hybrid", "Onsite"];

export default function CandidateSetupPage() {
  const { sessionId, mc, startRun, loading } = useSession();
  const [roles, setRoles] = useState<string[]>(["AI Engineer"]);
  const [modes, setModes] = useState<string[]>(["Remote"]);
  const [prefilledFromProfile, setPrefilledFromProfile] = useState(false);
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [profileError, setProfileError] = useState(false);
  const [system, setSystem] = useState<SystemView | null>(null);

  // Integration fix: a real user's saved Career Profile (target roles,
  // work-arrangement preference, location, resume file) should drive this
  // run instead of ever falling back to the synthetic demo candidate. This
  // only ever runs once, on mount, and only pre-fills form state/reads the
  // profile -- it never triggers a run or any network call to a
  // discovery/search provider by itself.
  useEffect(() => {
    let cancelled = false;
    const ownerId = getOwnerId();
    careerProfileApi
      .get(ownerId)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setProfileError(false);
        const profileRoles = p.target_roles.map((r) => r.title).filter((t) => ROLE_OPTIONS.includes(t));
        const profileModes = p.employment_preferences.work_arrangements.filter((m) =>
          MODE_OPTIONS.some((opt) => opt.toLowerCase() === m.toLowerCase())
        );
        if (profileRoles.length > 0) setRoles(profileRoles);
        if (profileModes.length > 0) {
          setModes(
            profileModes.map((m) => MODE_OPTIONS.find((opt) => opt.toLowerCase() === m.toLowerCase()) || m)
          );
        }
        if (profileRoles.length > 0 || profileModes.length > 0) setPrefilledFromProfile(true);
      })
      .catch(() => {
        // No Career Profile yet (404) or backend unreachable -- fall back
        // to the existing hardcoded defaults silently. This page must
        // never crash just because a profile doesn't exist yet, but it
        // DOES need to know "no profile" so it can block Run below.
        if (!cancelled) setProfileError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    api
      .system(sessionId)
      .then((s) => {
        if (!cancelled) setSystem(s);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  const resumeFilePath = profile?.resume_source.resume_file_path ?? null;
  const resumeUploadedAt = profile?.resume_source.uploaded_at ?? null;
  const hasResume = !!resumeFilePath;
  const locations = profile?.employment_preferences.locations ?? [];
  const employmentTypes = profile?.employment_preferences.employment_types ?? [];
  const compMin = profile?.employment_preferences.target_compensation_min ?? null;
  const compMax = profile?.employment_preferences.target_compensation_max ?? null;
  const compUnit = profile?.employment_preferences.compensation_unit ?? null;

  function compensationLabel(): string | null {
    if (compMin == null && compMax == null) return null;
    const unit = compUnit ? ` ${compUnit}` : "";
    if (compMin != null && compMax != null) return `${compMin} - ${compMax}${unit}`;
    if (compMin != null) return `${compMin}+${unit}`;
    return `up to ${compMax}${unit}`;
  }

  const discoverySourceLabel = system
    ? system.demo_mode || system.you_search === "UNAVAILABLE"
      ? "Demo Jobs (bundled sample data — live web search not configured)"
      : "Live Web via You.com"
    : null;

  // Real enforcement (api/main.py::start_run) rejects an unconfirmed
  // profile with a 403 -- this client-side gate mirrors that so the
  // button is genuinely disabled (not just decorative) before the
  // request is even made. profile.confirmed_at is cleared server-side
  // the instant a material field changes after confirmation (see
  // api/career_profile_routes.py's _invalidate_if_materially_changed),
  // so this always reflects the real, current gate state on reload.
  const isConfirmed = !!profile?.confirmed_at;
  const canRun = hasResume && roles.length > 0 && modes.length > 0 && isConfirmed;

  return (
    <div className="flex flex-col gap-5 max-w-[820px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Find Opportunities</h1>
        <p className="text-[12.5px] text-muted mt-0.5">
          Search and rank opportunities using your Career Profile.
        </p>
      </div>

      <div className="hl-card p-5 flex flex-col gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Target Roles</div>
          <div className="flex flex-wrap gap-2">
            {ROLE_OPTIONS.map((r) => (
              <button
                key={r}
                type="button"
                className={`hl-badge ${roles.includes(r) ? "hl-badge-violet" : "hl-badge-info"}`}
                onClick={() => toggle(roles, setRoles, r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Work Mode</div>
          <div className="flex flex-wrap gap-2">
            {MODE_OPTIONS.map((m) => (
              <button
                key={m}
                type="button"
                className={`hl-badge ${modes.includes(m) ? "hl-badge-violet" : "hl-badge-info"}`}
                onClick={() => toggle(modes, setModes, m)}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {hasResume ? (
          <div className="text-[11.5px] text-muted">
            Candidate source: Your Career Profile
            <br />
            Resume: uploaded {resumeUploadedAt ? new Date(resumeUploadedAt).toLocaleString() : "(date unknown)"}
          </div>
        ) : (
          <div className="text-[11.5px] text-amber">
            No resume on file yet. Upload a resume in{" "}
            <a href="/career-profile" className="underline font-semibold">
              Career Profile
            </a>{" "}
            before running discovery.
          </div>
        )}

        {profileError && !hasResume && (
          <div className="text-[11.5px] text-muted">
            Could not load your Career Profile. Create one and upload a resume in Career Profile first.
          </div>
        )}

        {hasResume && !isConfirmed && (
          <div className="text-[11.5px] text-amber">
            Review and confirm your Career Profile before searching for opportunities.{" "}
            <a href="/career-profile" className="underline font-semibold">
              Go to Career Profile
            </a>
          </div>
        )}

        {prefilledFromProfile && (
          <div className="text-[11.5px] text-green">
            Target roles and work mode pre-filled from your Career Profile — edit above if needed.
          </div>
        )}

        {/* Pre-search summary: everything below is a real value pulled from
            the Career Profile / session -- nothing here is fabricated. */}
        <div className="hl-card p-3 flex flex-col gap-1 bg-[var(--surface-2,rgba(255,255,255,0.03))]">
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-1">About to search</div>
          <div className="text-[11.5px]">Target Roles: {roles.length > 0 ? roles.join(", ") : "(none selected)"}</div>
          <div className="text-[11.5px]">
            Location: {locations.length > 0 ? locations.join(", ") : "(not set in Career Profile)"}
          </div>
          <div className="text-[11.5px]">Work Mode: {modes.length > 0 ? modes.join(", ") : "(none selected)"}</div>
          <div className="text-[11.5px]">
            Employment Type: {employmentTypes.length > 0 ? employmentTypes.join(", ") : "(not set in Career Profile)"}
          </div>
          <div className="text-[11.5px]">
            Compensation preference: {compensationLabel() ?? "(not set in Career Profile)"}
          </div>
          <div className="text-[11.5px]">
            Candidate source: {hasResume ? "Career Profile (resume on file)" : "No resume on file"}
          </div>
          <div className="text-[11.5px]">Discovery source: {discoverySourceLabel ?? "(loading…)"}</div>
        </div>

        <button
          className="hl-btn-primary self-start"
          disabled={loading || !canRun}
          title={
            !hasResume
              ? "Upload a resume to your Career Profile before running discovery."
              : !isConfirmed
                ? "Review and confirm your Career Profile before searching for opportunities."
                : undefined
          }
          onClick={() =>
            startRun({
              resume_path: resumeFilePath ?? undefined,
              target_roles: roles,
              work_modes: modes,
              owner_id: getOwnerId(),
            })
          }
        >
          {loading ? "Running…" : "Search Live Jobs"}
        </button>

        {mc?.has_run && (
          <p className="text-[11.5px] text-green">
            A discovery run has completed for this session — see Mission Control for results.
          </p>
        )}
      </div>
    </div>
  );
}
