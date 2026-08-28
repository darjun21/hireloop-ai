"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { careerProfileApi, getOwnerId } from "@/lib/career-profile-api";
import type {
  CareerProfile,
  ProfileCompleteness,
  ResumeUploadResponse,
} from "@/lib/career-profile-types";
import Badge from "@/components/Badge";

type Tab = "overview" | "personal" | "authorization" | "career" | "answers" | "resume" | "optional";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "personal", label: "Personal" },
  { id: "authorization", label: "Work Authorization" },
  { id: "career", label: "Career & Preferences" },
  { id: "answers", label: "Application Answers" },
  { id: "resume", label: "Resume & Evidence" },
  { id: "optional", label: "Optional" },
];

// Priority 3 fix: DEMOGRAPHICS_OPTIONAL/REFERENCES_OPTIONAL are explicitly
// optional (see src/services/career_profile_completeness.py -- they're
// excluded from overall_percent_complete's denominator entirely, by
// design, and always will be). The backend still returns NEEDS_REVIEW as
// their raw status for "not filled in yet" because CompletenessStatus has
// no dedicated value for that, so a brand-new user who has never touched
// Demographics/References would otherwise see the same "NEEDS REVIEW"
// wording used for genuinely required, incomplete sections -- which reads
// as broken. Every optional category is real -- suffixed "_OPTIONAL" -- so
// this label swap only ever applies there, and never changes the
// underlying status color/value used anywhere else.
function completenessBadge(status: string, isOptional = false) {
  if (isOptional && status !== "COMPLETE") {
    return <Badge label="OPTIONAL — NOT PROVIDED" kind="info" />;
  }
  return <Badge label={status.replace("_", " ")} kind={status === "COMPLETE" ? "success" : status === "MISSING" ? "danger" : "warning"} />;
}

export default function CareerProfilePage() {
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [completeness, setCompleteness] = useState<ProfileCompleteness | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Priority 7 (unsaved-changes guard): each editable Tab below reports
  // whether its form currently differs from what's saved via
  // onDirtyChange, and registers its own save() via onRegisterSave so
  // this bar/modal can trigger a real save without duplicating any
  // Tab-specific logic. Kept deliberately simple -- one shared dirty
  // flag for "the currently open tab has unsaved edits", not a
  // per-tab diff tracker.
  const [dirty, setDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);
  const [guardBusy, setGuardBusy] = useState(false);
  const [guardError, setGuardError] = useState<string | null>(null);
  const saveCurrentTabRef = useRef<(() => Promise<void>) | null>(null);

  // Real browser navigation/close/refresh while dirty -- the only text a
  // browser lets a page control here is whether the native confirm
  // appears at all, not its wording.
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  function handleTabChange(next: Tab) {
    if (next === tab) return;
    if (dirty) {
      setGuardError(null);
      setPendingTab(next);
    } else {
      setTab(next);
    }
  }

  async function confirmDiscard() {
    if (pendingTab) setTab(pendingTab);
    setPendingTab(null);
    setDirty(false);
    setGuardError(null);
  }

  async function confirmSaveAndContinue() {
    if (!saveCurrentTabRef.current) {
      // No save handler registered for this tab (shouldn't happen while
      // dirty is true) -- fail safe by not navigating away silently.
      setGuardError("Could not find a save action for this section. Discard or stay here.");
      return;
    }
    setGuardBusy(true);
    setGuardError(null);
    try {
      await saveCurrentTabRef.current();
      if (pendingTab) setTab(pendingTab);
      setPendingTab(null);
      setDirty(false);
    } catch (e) {
      setGuardError(e instanceof Error ? e.message : "Save failed. Your edits are still here.");
    } finally {
      setGuardBusy(false);
    }
  }

  const load = useCallback(async () => {
    const oid = getOwnerId();
    setOwnerId(oid);
    setLoading(true);
    try {
      const p = await careerProfileApi.getOrCreate(oid);
      setProfile(p);
      const c = await careerProfileApi.completeness(oid);
      setCompleteness(c);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach the Career Profile API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data fetch on mount
    load();
  }, [load]);

  async function refreshAfterSave(next: CareerProfile) {
    setProfile(next);
    setSavedAt(new Date().toLocaleTimeString());
    if (ownerId) {
      const c = await careerProfileApi.completeness(ownerId);
      setCompleteness(c);
    }
  }

  if (loading && !profile) {
    return <div className="text-[13px] text-muted">Loading career profile…</div>;
  }
  if (error) {
    return (
      <div className="hl-card p-5 text-[13px] text-red">
        {error}
        <div className="mt-2 text-muted text-[11.5px]">
          Is the API bridge running? (uvicorn api.main:app --reload --port 8000)
        </div>
        <button className="hl-btn-secondary mt-3" onClick={() => load()}>
          Retry
        </button>
      </div>
    );
  }
  if (!profile || !ownerId) return null;

  return (
    <div className="flex flex-col gap-5 max-w-[980px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">My Career Profile</h1>
        <p className="text-[12.5px] text-muted mt-0.5">
          Your persistent, editable profile — separate from any single discovery run. Nothing here is shared with
          the Certification Demo, and nothing is submitted anywhere automatically.
        </p>
      </div>

      {savedAt && <div className="text-[11.5px] text-green">Saved at {savedAt}</div>}

      {pendingTab && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="hl-card p-5 max-w-[420px] w-full flex flex-col gap-3">
            <div className="text-[14px] font-bold">You have unsaved changes.</div>
            <div className="text-[12px] text-muted">
              Leaving this section now will lose your edits here — they haven&apos;t been saved yet.
            </div>
            {guardError && <div className="text-[11.5px] text-red">{guardError}</div>}
            <div className="flex flex-col gap-2 mt-1">
              <button className="hl-btn-primary" onClick={confirmSaveAndContinue} disabled={guardBusy}>
                {guardBusy ? "Saving…" : "Save & Continue"}
              </button>
              <button className="hl-btn-secondary" onClick={confirmDiscard} disabled={guardBusy}>
                Discard Changes
              </button>
              <button
                className="text-[11.5px] text-muted hover:text-text"
                onClick={() => {
                  setPendingTab(null);
                  setGuardError(null);
                }}
                disabled={guardBusy}
              >
                Stay Here
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => handleTabChange(t.id)}
            className={`px-3 py-2 text-[12.5px] font-semibold whitespace-nowrap border-b-2 -mb-px ${
              tab === t.id ? "border-cyan text-text" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {t.label}
            {dirty && tab === t.id ? " •" : ""}
          </button>
        ))}
      </div>

      {tab === "overview" && completeness && (
        <OverviewTab
          completeness={completeness}
          profile={profile}
          onNavigate={handleTabChange}
          ownerId={ownerId}
          onSaved={refreshAfterSave}
        />
      )}
      {tab === "personal" && (
        <PersonalTab
          ownerId={ownerId}
          profile={profile}
          onSaved={refreshAfterSave}
          onDirtyChange={setDirty}
          onRegisterSave={(fn) => (saveCurrentTabRef.current = fn)}
        />
      )}
      {tab === "authorization" && (
        <AuthorizationTab
          ownerId={ownerId}
          profile={profile}
          onSaved={refreshAfterSave}
          onDirtyChange={setDirty}
          onRegisterSave={(fn) => (saveCurrentTabRef.current = fn)}
        />
      )}
      {tab === "career" && (
        <CareerTab
          ownerId={ownerId}
          profile={profile}
          onSaved={refreshAfterSave}
          onDirtyChange={setDirty}
          onRegisterSave={(fn) => (saveCurrentTabRef.current = fn)}
        />
      )}
      {tab === "answers" && (
        <AnswersTab
          ownerId={ownerId}
          profile={profile}
          onSaved={refreshAfterSave}
          onDirtyChange={setDirty}
          onRegisterSave={(fn) => (saveCurrentTabRef.current = fn)}
        />
      )}
      {tab === "resume" && <ResumeTab ownerId={ownerId} profile={profile} onSaved={refreshAfterSave} />}
      {tab === "optional" && (
        <OptionalTab
          ownerId={ownerId}
          profile={profile}
          onSaved={refreshAfterSave}
          onDirtyChange={setDirty}
          onRegisterSave={(fn) => (saveCurrentTabRef.current = fn)}
        />
      )}
    </div>
  );
}

function OverviewTab({
  completeness,
  profile,
  onNavigate,
  ownerId,
  onSaved,
}: {
  completeness: ProfileCompleteness;
  profile: CareerProfile;
  onNavigate: (t: Tab) => void;
  ownerId: string;
  onSaved: (p: CareerProfile) => void;
}) {
  const required = completeness.categories.filter((c) => !c.category.endsWith("_OPTIONAL"));
  const optional = completeness.categories.filter((c) => c.category.endsWith("_OPTIONAL"));
  const targets: Record<string, Tab> = {
    IDENTITY_CONTACT: "personal",
    RESUME: "resume",
    WORK_AUTHORIZATION: "authorization",
    TARGET_ROLES: "career",
    PREFERENCES: "career",
    PROFESSIONAL_HISTORY: "resume",
    DEMOGRAPHICS_OPTIONAL: "optional",
    REFERENCES_OPTIONAL: "optional",
  };

  // Priority 4 (onboarding guidance): a brand-new profile has no resume on
  // file yet -- that's the natural starting point (Upload Resume feeds
  // the merge/diff preview that pre-fills everything else). This is a
  // small addition to the existing overview tab, not a new wizard.
  const hasResume = !!profile.resume_source.resume_file_path || !!profile.resume_source.uploaded_at;
  const ONBOARDING_STEPS: { label: string; done: boolean; target: Tab }[] = [
    { label: "Upload Resume", done: hasResume, target: "resume" },
    { label: "Review Extracted Profile", done: profile.skills.length > 0 || profile.work_experience.length > 0, target: "resume" },
    { label: "Personal Info", done: !!profile.personal_info?.first_name, target: "personal" },
    { label: "Work Authorization", done: !!profile.work_authorization?.authorized_to_work, target: "authorization" },
    { label: "Preferences", done: profile.employment_preferences.locations.length > 0, target: "career" },
    { label: "Confirm", done: !!profile.confirmed_at, target: "overview" },
    { label: "Find Opportunities", done: false, target: "overview" },
  ];

  return (
    <div className="flex flex-col gap-4">
      {!hasResume && (
        <div className="hl-card p-5 border-cyan/40 flex flex-col gap-2">
          <div className="text-[13px] font-bold">New here? Start with your resume.</div>
          <div className="text-[11.5px] text-muted">
            Uploading a resume extracts your work history, skills, and education automatically — you review and
            confirm before anything is saved.
          </div>
          <button className="hl-btn-primary self-start mt-1" onClick={() => onNavigate("resume")}>
            Upload Resume
          </button>
        </div>
      )}

      <div className="hl-card p-4">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Recommended order</div>
        <div className="flex flex-wrap items-center gap-1.5">
          {ONBOARDING_STEPS.map((step, i) => {
            const isLast = i === ONBOARDING_STEPS.length - 1;
            const badgeClass = `text-[11px] font-semibold px-2 py-1 rounded-full border ${
              step.done
                ? "border-green/50 text-green bg-green/10"
                : "border-border text-muted hover:text-text hover:border-cyan/50"
            }`;
            return (
              <span key={step.label} className="flex items-center gap-1.5">
                {isLast ? (
                  <a href="/candidate-setup" className={badgeClass}>
                    {step.label}
                  </a>
                ) : (
                  <button onClick={() => onNavigate(step.target)} className={badgeClass}>
                    {step.done ? "✓ " : ""}
                    {step.label}
                  </button>
                )}
                {!isLast && <span className="text-muted text-[11px]">→</span>}
              </span>
            );
          })}
        </div>
      </div>

      <div className="hl-card p-5">
        <div className="flex items-baseline justify-between">
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Overall completeness</div>
          <div className="text-2xl font-extrabold">{completeness.overall_percent_complete}%</div>
        </div>
        <div className="text-[11px] text-muted mt-1">
          Deterministic — based on required categories only. Optional demographics/references never affect this
          number.
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {required.map((c) => (
          <button
            key={c.category}
            onClick={() => onNavigate(targets[c.category] || "overview")}
            className="hl-card p-4 text-left flex flex-col gap-1.5 hover:border-cyan/50"
          >
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] font-semibold">{c.category.replace(/_/g, " ")}</span>
              {completenessBadge(c.status)}
            </div>
            {/* Part 3-4 fix: itemized, specific reasons instead of a bare
                "NEEDS REVIEW" badge with no explanation. Every string here
                comes straight from
                src/services/career_profile_completeness.py's
                professional_history_review_reasons() -- never invented
                client-side. */}
            {c.review_reasons.length > 0 && (
              <ul className="text-[11px] text-muted list-disc list-inside space-y-0.5">
                {c.review_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
          </button>
        ))}
      </div>

      <ConfirmProfileCard
        completeness={completeness}
        profile={profile}
        onNavigate={onNavigate}
        ownerId={ownerId}
        onSaved={onSaved}
      />

      <div className="text-[11px] font-bold uppercase tracking-wide text-muted mt-2">Optional (never required)</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {optional.map((c) => (
          <button
            key={c.category}
            onClick={() => onNavigate(targets[c.category] || "overview")}
            className="hl-card p-4 text-left flex items-center justify-between hover:border-cyan/50"
          >
            <span className="text-[12.5px] font-semibold">{c.category.replace(/_OPTIONAL/, "").replace(/_/g, " ")}</span>
            {completenessBadge(c.status, true)}
          </button>
        ))}
      </div>

      <div className="hl-card p-4 text-[11.5px] text-muted">
        Resume version: <strong className="text-text">v{profile.resume_source.parsed_profile_version}</strong>{" "}
        {profile.resume_source.uploaded_at ? `· last uploaded ${new Date(profile.resume_source.uploaded_at).toLocaleString()}` : "· no resume uploaded yet"}
      </div>
    </div>
  );
}

// Part 12: explicit "Confirm Profile" gate. Backed by a real endpoint
// (api/career_profile_routes.py::confirm_profile) that only succeeds once
// every REQUIRED completeness category is COMPLETE -- this button is
// disabled client-side for the same reason, but the server enforces it
// too (409 otherwise), so this can never be bypassed by calling the API
// directly. Does not itself start discovery -- "Find Opportunities"
// remains a separate, explicit action on /candidate-setup.
function ConfirmProfileCard({
  completeness,
  profile,
  onNavigate,
  ownerId,
  onSaved,
}: {
  completeness: ProfileCompleteness;
  profile: CareerProfile;
  onNavigate: (t: Tab) => void;
  ownerId: string;
  onSaved: (p: CareerProfile) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const required = completeness.categories.filter((c) => !c.category.endsWith("_OPTIONAL"));
  const allComplete = required.every((c) => c.status === "COMPLETE");

  async function confirm() {
    setBusy(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.confirmProfile(ownerId);
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to confirm profile.");
    } finally {
      setBusy(false);
    }
  }

  if (profile.confirmed_at) {
    return (
      <div className="hl-card p-5 border-green/40 flex items-center justify-between">
        <div>
          <div className="text-[13px] font-bold text-green">Profile confirmed</div>
          <div className="text-[11.5px] text-muted mt-0.5">
            Confirmed {new Date(profile.confirmed_at).toLocaleString()}. You can now find opportunities.
          </div>
        </div>
        <a href="/candidate-setup" className="hl-btn-primary">
          Find Opportunities
        </a>
      </div>
    );
  }

  return (
    <div className="hl-card p-5 flex flex-col gap-2">
      <div className="text-[13px] font-bold">Confirm Profile</div>
      <div className="text-[11.5px] text-muted">
        {allComplete
          ? "Every required section is complete. Confirming locks in your profile as reviewed."
          : "Complete every required section above (no NEEDS REVIEW / MISSING badges) before confirming."}
      </div>
      {err && <div className="text-[11.5px] text-red">{err}</div>}
      <div className="flex gap-2">
        <button className="hl-btn-primary self-start" onClick={confirm} disabled={!allComplete || busy}>
          {busy ? "Confirming…" : "Confirm Profile"}
        </button>
        {!allComplete && (
          <button className="hl-btn-secondary self-start" onClick={() => onNavigate("resume")}>
            Review Resume & Evidence
          </button>
        )}
      </div>
    </div>
  );
}

function AuthBoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (v: boolean | null) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-[11.5px]">
      <span className="text-muted font-semibold">{label}</span>
      <select
        className="hl-input"
        value={value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "true")}
      >
        <option value="">Not specified</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  );
}

function SaveBar({ onSave, saving, error }: { onSave: () => void; saving: boolean; error?: string | null }) {
  return (
    <div className="flex flex-col gap-2 items-start">
      <button className="hl-btn-primary self-start" onClick={onSave} disabled={saving}>
        {saving ? "Saving…" : "Save Changes"}
      </button>
      {error && <div className="text-[11.5px] text-red">{error}</div>}
    </div>
  );
}

// Every Tab's save() below catches its own errors (rather than letting a
// failed fetch propagate as an unhandled promise rejection) -- an
// uncaught rejection from an onClick handler is exactly what was
// crashing this page into Next.js's runtime error overlay on a network
// failure. errorMessage() extracts the readable, already-differentiated
// message an ApiError carries (network vs. 404 vs. 409 vs. 422 vs. 500);
// see lib/api-config.ts.
function errorMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

// Priority 7 (unsaved-changes guard): shared by every editable Tab below.
// Compares the current form object to a snapshot taken when the Tab was
// last "clean" (mount or last successful save) and reports the result up
// via onDirtyChange -- no per-field wiring needed at each onChange call
// site. useDirtyForm also hands back a `markClean()` to call right after
// a successful save.
function useDirtyForm<T>(form: T, onDirtyChange?: (dirty: boolean) => void) {
  const cleanSnapshotRef = useRef(JSON.stringify(form));
  useEffect(() => {
    onDirtyChange?.(JSON.stringify(form) !== cleanSnapshotRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);
  return {
    markClean: () => {
      cleanSnapshotRef.current = JSON.stringify(form);
      onDirtyChange?.(false);
    },
  };
}

interface DirtyTrackedTabProps {
  onDirtyChange?: (dirty: boolean) => void;
  onRegisterSave?: (fn: () => Promise<void>) => void;
}

function PersonalTab({
  ownerId,
  profile,
  onSaved,
  onDirtyChange,
  onRegisterSave,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
} & DirtyTrackedTabProps) {
  const pi = profile.personal_info;
  const [form, setForm] = useState({
    first_name: pi?.first_name || "",
    middle_name: pi?.middle_name || "",
    last_name: pi?.last_name || "",
    preferred_name: pi?.preferred_name || "",
    professional_email: pi?.professional_email || "",
    phone: pi?.phone || "",
    linkedin_url: pi?.linkedin_url || "",
    city: pi?.city || "",
    state: pi?.state || "",
    country: pi?.country || "",
    postal_code: pi?.postal_code || "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { markClean } = useDirtyForm(form, onDirtyChange);

  // Returns success/failure instead of throwing -- the plain "Save
  // Changes" button below calls this directly (onClick={save}), and a
  // rejected promise from an onClick handler with no .catch anywhere is
  // an UNCAUGHT PROMISE REJECTION in the browser (exactly the failure
  // mode api-config.ts's ApiError handling exists to prevent). Only the
  // unsaved-changes-guard's registered save (below) needs throw-on-
  // failure semantics, and it gets that by wrapping this return value,
  // not by making save() itself throw.
  async function save(): Promise<boolean> {
    setSaving(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.updatePersonalInfo(ownerId, form);
      onSaved(updated);
      markClean();
      return true;
    } catch (e) {
      setErr(errorMessage(e, "Failed to save personal info."));
      return false;
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    onRegisterSave?.(async () => {
      if (!(await save())) throw new Error("Save failed. See the error shown on this tab.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  const fields: [keyof typeof form, string][] = [
    ["first_name", "First name"],
    ["middle_name", "Middle name"],
    ["last_name", "Last name"],
    ["preferred_name", "Preferred name"],
    ["professional_email", "Professional email"],
    ["phone", "Phone"],
    ["linkedin_url", "LinkedIn URL"],
    ["city", "City"],
    ["state", "State / Province"],
    ["country", "Country"],
    ["postal_code", "Postal code"],
  ];

  return (
    <div className="hl-card p-5 flex flex-col gap-4 max-w-[640px]">
      <div className="text-[11.5px] text-muted">
        No full street address is collected here — only city/state/country/postal, by design.
      </div>
      <div className="grid grid-cols-2 gap-3">
        {fields.map(([key, label]) => (
          <label key={key} className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">{label}</span>
            <input
              className="hl-input"
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <SaveBar onSave={save} saving={saving} error={err} />
    </div>
  );
}

function AuthorizationTab({
  ownerId,
  profile,
  onSaved,
  onDirtyChange,
  onRegisterSave,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
} & DirtyTrackedTabProps) {
  const wa = profile.work_authorization;
  const [form, setForm] = useState({
    target_country: wa?.target_country || "",
    authorized_to_work: wa?.authorized_to_work ?? null,
    authorization_type: wa?.authorization_type || "",
    requires_sponsorship_now: wa?.requires_sponsorship_now ?? null,
    requires_sponsorship_future: wa?.requires_sponsorship_future ?? null,
    expiration_date: wa?.expiration_date || "",
    notes: wa?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { markClean } = useDirtyForm(form, onDirtyChange);

  async function save(): Promise<boolean> {
    setSaving(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.updateWorkAuthorization(ownerId, form);
      onSaved(updated);
      markClean();
      return true;
    } catch (e) {
      setErr(errorMessage(e, "Failed to save work authorization."));
      return false;
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    onRegisterSave?.(async () => {
      if (!(await save())) throw new Error("Save failed. See the error shown on this tab.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  return (
    <div className="hl-card p-5 flex flex-col gap-4 max-w-[640px]">
      <div className="text-[11.5px] text-muted">
        Stored exactly as you confirm it here. Never inferred from your resume — the resume parser never touches
        this section.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Target country</span>
          <input className="hl-input" value={form.target_country} onChange={(e) => setForm({ ...form, target_country: e.target.value })} />
        </label>
        <AuthBoolField
          label="Authorized to work"
          value={form.authorized_to_work}
          onChange={(v) => setForm({ ...form, authorized_to_work: v })}
        />
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Authorization / status type</span>
          <input
            className="hl-input"
            placeholder="e.g. US Citizen, H1B, OPT"
            value={form.authorization_type}
            onChange={(e) => setForm({ ...form, authorization_type: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Expiration date (optional)</span>
          <input className="hl-input" value={form.expiration_date} onChange={(e) => setForm({ ...form, expiration_date: e.target.value })} />
        </label>
        <AuthBoolField
          label="Requires sponsorship now"
          value={form.requires_sponsorship_now}
          onChange={(v) => setForm({ ...form, requires_sponsorship_now: v })}
        />
        <AuthBoolField
          label="Will require sponsorship in future"
          value={form.requires_sponsorship_future}
          onChange={(v) => setForm({ ...form, requires_sponsorship_future: v })}
        />
      </div>
      <label className="flex flex-col gap-1 text-[11.5px]">
        <span className="text-muted font-semibold">Notes</span>
        <textarea className="hl-input" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      </label>
      <SaveBar onSave={save} saving={saving} error={err} />
    </div>
  );
}

function CareerTab({
  ownerId,
  profile,
  onSaved,
  onDirtyChange,
  onRegisterSave,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
} & DirtyTrackedTabProps) {
  const [rolesText, setRolesText] = useState(profile.target_roles.map((r) => r.title).join(", "));
  const prefs = profile.employment_preferences;
  const [form, setForm] = useState({
    locations: prefs.locations.join(", "),
    work_arrangements: prefs.work_arrangements.join(", "),
    employment_types: prefs.employment_types.join(", "),
    target_compensation_min: prefs.target_compensation_min ?? "",
    target_compensation_max: prefs.target_compensation_max ?? "",
    compensation_unit: prefs.compensation_unit || "",
    relocation_willing: prefs.relocation_willing ?? null,
    travel_willingness: prefs.travel_willingness || "",
    industry_preferences: prefs.industry_preferences.join(", "),
    company_size_preference: prefs.company_size_preference || "",
    excluded_companies: prefs.excluded_companies.join(", "),
    preferred_companies: prefs.preferred_companies.join(", "),
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { markClean } = useDirtyForm({ rolesText, form }, onDirtyChange);

  function toList(s: string): string[] {
    return s
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  async function save(): Promise<boolean> {
    setSaving(true);
    setErr(null);
    try {
      const roles = toList(rolesText).map((title) => ({ title, priority: null }));
      let updated = await careerProfileApi.updateTargetRoles(ownerId, roles);
      updated = await careerProfileApi.updatePreferences(ownerId, {
        locations: toList(form.locations),
        work_arrangements: toList(form.work_arrangements),
        employment_types: toList(form.employment_types),
        target_compensation_min: form.target_compensation_min === "" ? null : Number(form.target_compensation_min),
        target_compensation_max: form.target_compensation_max === "" ? null : Number(form.target_compensation_max),
        compensation_unit: form.compensation_unit || null,
        relocation_willing: form.relocation_willing,
        travel_willingness: form.travel_willingness || null,
        industry_preferences: toList(form.industry_preferences),
        company_size_preference: form.company_size_preference || null,
        excluded_companies: toList(form.excluded_companies),
        preferred_companies: toList(form.preferred_companies),
      });
      onSaved(updated);
      markClean();
      return true;
    } catch (e) {
      setErr(errorMessage(e, "Failed to save career preferences."));
      return false;
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    onRegisterSave?.(async () => {
      if (!(await save())) throw new Error("Save failed. See the error shown on this tab.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rolesText, form]);

  return (
    <div className="flex flex-col gap-4">
      <div className="hl-card p-5 flex flex-col gap-3 max-w-[640px]">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Target roles</div>
        <input
          className="hl-input"
          placeholder="Comma-separated, e.g. AI Engineer, ML Engineer"
          value={rolesText}
          onChange={(e) => setRolesText(e.target.value)}
        />
        <div className="text-[11px] text-muted">Free text — not a fixed dropdown list.</div>
      </div>

      <div className="hl-card p-5 flex flex-col gap-4 max-w-[640px]">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Employment preferences</div>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Locations</span>
            <input className="hl-input" value={form.locations} onChange={(e) => setForm({ ...form, locations: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Work arrangement (Remote/Hybrid/Onsite/Flexible)</span>
            <input className="hl-input" value={form.work_arrangements} onChange={(e) => setForm({ ...form, work_arrangements: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Employment type</span>
            <input className="hl-input" value={form.employment_types} onChange={(e) => setForm({ ...form, employment_types: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Compensation unit</span>
            <input className="hl-input" value={form.compensation_unit} onChange={(e) => setForm({ ...form, compensation_unit: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Target compensation min</span>
            <input className="hl-input" value={form.target_compensation_min} onChange={(e) => setForm({ ...form, target_compensation_min: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Target compensation max</span>
            <input className="hl-input" value={form.target_compensation_max} onChange={(e) => setForm({ ...form, target_compensation_max: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Relocation willing</span>
            <select
              className="hl-input"
              value={form.relocation_willing === null ? "" : String(form.relocation_willing)}
              onChange={(e) => setForm({ ...form, relocation_willing: e.target.value === "" ? null : e.target.value === "true" })}
            >
              <option value="">Not specified</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Travel willingness</span>
            <input className="hl-input" value={form.travel_willingness} onChange={(e) => setForm({ ...form, travel_willingness: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Industry preferences</span>
            <input className="hl-input" value={form.industry_preferences} onChange={(e) => setForm({ ...form, industry_preferences: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Company size preference</span>
            <input className="hl-input" value={form.company_size_preference} onChange={(e) => setForm({ ...form, company_size_preference: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Excluded companies</span>
            <input className="hl-input" value={form.excluded_companies} onChange={(e) => setForm({ ...form, excluded_companies: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1 text-[11.5px]">
            <span className="text-muted font-semibold">Preferred companies</span>
            <input className="hl-input" value={form.preferred_companies} onChange={(e) => setForm({ ...form, preferred_companies: e.target.value })} />
          </label>
        </div>
        <SaveBar onSave={save} saving={saving} error={err} />
      </div>
    </div>
  );
}

function AnswersTab({
  ownerId,
  profile,
  onSaved,
  onDirtyChange,
  onRegisterSave,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
} & DirtyTrackedTabProps) {
  const a = profile.application_answers;
  const [form, setForm] = useState({
    authorized_to_work: a.authorized_to_work,
    requires_sponsorship: a.requires_sponsorship,
    willing_to_relocate: a.willing_to_relocate,
    earliest_start_date: a.earliest_start_date || "",
    notice_period: a.notice_period || "",
    desired_compensation: a.desired_compensation ?? "",
    compensation_unit: a.compensation_unit || "",
    preferred_employment_type: a.preferred_employment_type || "",
    preferred_work_mode: a.preferred_work_mode || "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { markClean } = useDirtyForm(form, onDirtyChange);

  async function save(): Promise<boolean> {
    setSaving(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.updateApplicationAnswers(ownerId, {
        ...form,
        desired_compensation: form.desired_compensation === "" ? null : Number(form.desired_compensation),
        preferred_employment_type: form.preferred_employment_type || null,
        preferred_work_mode: form.preferred_work_mode || null,
      });
      onSaved(updated);
      markClean();
      return true;
    } catch (e) {
      setErr(errorMessage(e, "Failed to save application answers."));
      return false;
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    onRegisterSave?.(async () => {
      if (!(await save())) throw new Error("Save failed. See the error shown on this tab.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  return (
    <div className="hl-card p-5 flex flex-col gap-4 max-w-[640px]">
      <div className="text-[11.5px] text-muted">
        Reusable answers for application questions — a genuinely separate structure from your resume facts. Editing
        these never changes your resume-derived skills or work history.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Earliest start date</span>
          <input className="hl-input" value={form.earliest_start_date} onChange={(e) => setForm({ ...form, earliest_start_date: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Notice period</span>
          <input className="hl-input" value={form.notice_period} onChange={(e) => setForm({ ...form, notice_period: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Desired compensation</span>
          <input className="hl-input" value={form.desired_compensation} onChange={(e) => setForm({ ...form, desired_compensation: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-[11.5px]">
          <span className="text-muted font-semibold">Compensation unit</span>
          <input className="hl-input" value={form.compensation_unit} onChange={(e) => setForm({ ...form, compensation_unit: e.target.value })} />
        </label>
      </div>
      <SaveBar onSave={save} saving={saving} error={err} />
    </div>
  );
}

function ResumeTab({
  ownerId,
  profile,
  onSaved,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
}) {
  const [uploadResult, setUploadResult] = useState<ResumeUploadResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const result = await careerProfileApi.uploadResume(ownerId, file);
      setUploadResult(result);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!uploadResult) return;
    setBusy(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.applyResumeUpdate(ownerId, uploadResult.upload_id);
      onSaved(updated);
      setUploadResult(null);
    } catch (ex) {
      setErr(errorMessage(ex, "Failed to apply profile update."));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!uploadResult) return;
    setBusy(true);
    setErr(null);
    try {
      await careerProfileApi.cancelResumeUpdate(ownerId, uploadResult.upload_id);
      setUploadResult(null);
    } catch (ex) {
      setErr(errorMessage(ex, "Failed to cancel profile update."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="hl-card p-5 flex flex-col gap-3">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Current resume</div>
        <div className="text-[12.5px]">
          Version <strong>v{profile.resume_source.parsed_profile_version}</strong>
          {profile.resume_source.original_filename ? ` — ${profile.resume_source.original_filename}` : ""}
        </div>
        <div className="text-[11.5px] text-muted">
          {profile.resume_source.uploaded_at
            ? `Uploaded ${new Date(profile.resume_source.uploaded_at).toLocaleString()}`
            : "No resume uploaded yet."}
        </div>

        <label className="hl-btn-secondary self-start cursor-pointer">
          Upload New Resume
          <input type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={onFile} disabled={busy} />
        </label>
        {err && <div className="text-[11.5px] text-red">{err}</div>}
      </div>

      {uploadResult && (
        <div className="hl-card p-5 flex flex-col gap-3">
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Profile Update Preview</div>
          <DiffSection title="New skills" items={uploadResult.diff.new_skills} kind="success" />
          <DiffSection title="New work experience" items={uploadResult.diff.new_work_experience} kind="success" />
          <DiffSection title="New education" items={uploadResult.diff.new_education} kind="success" />
          <DiffSection title="New certifications" items={uploadResult.diff.new_certifications} kind="success" />
          <DiffSection title="Changed work experience" items={uploadResult.diff.changed_work_experience} kind="warning" />
          {uploadResult.diff.potential_conflicts.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-red mb-1">
                Needs review — manually confirmed data not in new resume
              </div>
              {uploadResult.diff.potential_conflicts.map((c, i) => (
                <div key={i} className="text-[11.5px] text-text">
                  {c.description}
                </div>
              ))}
              <div className="text-[11px] text-muted mt-1">
                These will NOT be deleted automatically — they stay on your profile until you edit them yourself.
              </div>
            </div>
          )}
          {uploadResult.validation_warnings.length > 0 && (
            <DiffSection title="Extraction warnings" items={uploadResult.validation_warnings} kind="warning" />
          )}
          <div className="flex gap-2">
            <button className="hl-btn-primary" onClick={apply} disabled={busy}>
              Apply Profile Update
            </button>
            <button className="hl-btn-secondary" onClick={cancel} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Parts 5-8: the full structured profile, not just a flat skills
          list. This is the actual root-cause fix for "Resume & Evidence
          only shows 3 skills" -- the backend/API always returned the full
          CareerProfile (summary/skills/work experience/projects/
          education/certifications/languages/warnings); this tab simply
          never rendered anything past `profile.skills` until now. */}
      {profile.professional_summary && (
        <div className="hl-card p-5 flex flex-col gap-2">
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Professional Summary</div>
          <div className="text-[12.5px] leading-relaxed">{profile.professional_summary}</div>
        </div>
      )}

      <SkillsSection ownerId={ownerId} profile={profile} onSaved={onSaved} />
      <WorkExperienceSection ownerId={ownerId} profile={profile} onSaved={onSaved} />
      <ProjectsSection ownerId={ownerId} profile={profile} onSaved={onSaved} />
      <EducationSection ownerId={ownerId} profile={profile} onSaved={onSaved} />
      <CertificationsSection profile={profile} />
      <LanguagesSection profile={profile} />
      <ExtractionWarningsSection profile={profile} />
    </div>
  );
}

function SourceBadge({ provenance }: { provenance: string }) {
  const reviewed = provenance === "USER_CONFIRMED" || provenance === "HUMAN_CONFIRMATION";
  return (
    <span
      className={`text-[10.5px] font-semibold px-1.5 py-0.5 rounded border ${
        reviewed ? "border-green/40 text-green bg-green/10" : "border-amber/40 text-amber bg-amber/10"
      }`}
      title={`SOURCE: ${provenance}`}
    >
      {reviewed ? "reviewed" : "from resume · needs review"}
    </span>
  );
}

function SkillsSection({
  ownerId,
  profile,
  onSaved,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function confirm(name: string) {
    setBusy(name);
    setErr(null);
    try {
      const updated = await careerProfileApi.reviewSkill(ownerId, name);
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to confirm skill.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="hl-card p-5 flex flex-col gap-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Skills on file ({profile.skills.length})
      </div>
      {err && <div className="text-[11.5px] text-red">{err}</div>}
      <div className="flex flex-col gap-2">
        {profile.skills.map((s) => (
          <div key={s.name} className="flex items-center flex-wrap gap-2 text-[12px]">
            <span className="hl-badge hl-badge-info">{s.name}</span>
            <SourceBadge provenance={s.provenance} />
            {s.evidence_summaries.length > 0 ? (
              <span className="text-muted text-[11px]">
                Evidence: {s.evidence_summaries.join("; ")}
              </span>
            ) : (
              <span className="text-muted text-[11px] italic">No evidence source on file.</span>
            )}
            {s.provenance === "RESUME_DERIVED" && (
              <button
                className="text-[11px] text-cyan hover:underline"
                onClick={() => confirm(s.name)}
                disabled={busy === s.name}
              >
                {busy === s.name ? "Confirming…" : "Confirm"}
              </button>
            )}
          </div>
        ))}
        {profile.skills.length === 0 && <span className="text-[11.5px] text-muted">No skills on file yet.</span>}
      </div>
    </div>
  );
}

function WorkExperienceSection({
  ownerId,
  profile,
  onSaved,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState({ start_date: "", end_date: "", is_current: false });

  function missingFieldNote(w: CareerProfile["work_experience"][number]): string | null {
    const gaps: string[] = [];
    if (!w.start_date) gaps.push("missing start date");
    if (!w.end_date) gaps.push("missing end date (or not marked current)");
    if (w.provenance === "RESUME_DERIVED") gaps.push("not yet reviewed");
    return gaps.length > 0 ? gaps.join(", ") : null;
  }

  function startEdit(entryId: string, w: CareerProfile["work_experience"][number]) {
    setEditing(entryId);
    setForm({ start_date: w.start_date || "", end_date: w.end_date || "", is_current: w.end_date === "Present" });
  }

  async function save(entryId: string) {
    setBusy(entryId);
    setErr(null);
    try {
      const updated = await careerProfileApi.reviewWorkExperience(ownerId, entryId, {
        start_date: form.start_date || null,
        end_date: form.is_current ? null : form.end_date || null,
        is_current: form.is_current,
      });
      onSaved(updated);
      setEditing(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save work experience.");
    } finally {
      setBusy(null);
    }
  }

  async function confirmAsIs(entryId: string) {
    setBusy(entryId);
    setErr(null);
    try {
      const updated = await careerProfileApi.reviewWorkExperience(ownerId, entryId, {});
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to confirm work experience.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="hl-card p-5 flex flex-col gap-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Work Experience ({profile.work_experience.length})
      </div>
      {err && <div className="text-[11.5px] text-red">{err}</div>}
      {profile.work_experience.length === 0 && (
        <span className="text-[11.5px] text-muted">
          No work experience on file.
          {profile.projects.length > 0
            ? ` ${profile.projects.length} project(s) were extracted instead — see Projects below.`
            : ""}
        </span>
      )}
      {profile.work_experience.map((w) => {
        const note = missingFieldNote(w);
        return (
          <div key={w.entry_id} className="border border-border rounded-md p-3 flex flex-col gap-1.5">
            <div className="flex items-center justify-between flex-wrap gap-1.5">
              <div className="text-[12.5px] font-semibold">
                {w.title} <span className="text-muted font-normal">at {w.company}</span>
              </div>
              <SourceBadge provenance={w.provenance} />
            </div>
            <div className="text-[11.5px] text-muted">
              {w.start_date || "?"} — {w.end_date || "?"}
            </div>
            {w.description && <div className="text-[11.5px]">{w.description}</div>}
            {w.skills_used.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {w.skills_used.map((s) => (
                  <span key={s} className="hl-badge hl-badge-info text-[10.5px]">
                    {s}
                  </span>
                ))}
              </div>
            )}
            {note && (
              <div className="text-[11px] text-amber font-semibold">NEEDS REVIEW — {note}</div>
            )}
            {editing === w.entry_id ? (
              <div className="flex flex-wrap items-end gap-2 mt-1">
                <label className="flex flex-col gap-1 text-[11px]">
                  <span className="text-muted">Start date</span>
                  <input
                    className="hl-input"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-[11px]">
                  <span className="text-muted">End date</span>
                  <input
                    className="hl-input"
                    value={form.end_date}
                    disabled={form.is_current}
                    onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                  />
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-muted">
                  <input
                    type="checkbox"
                    checked={form.is_current}
                    onChange={(e) => setForm({ ...form, is_current: e.target.checked })}
                  />
                  Still working here
                </label>
                <button className="hl-btn-primary" onClick={() => save(w.entry_id)} disabled={busy === w.entry_id}>
                  {busy === w.entry_id ? "Saving…" : "Save"}
                </button>
                <button className="hl-btn-secondary" onClick={() => setEditing(null)}>
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex gap-2 mt-1">
                <button className="text-[11px] text-cyan hover:underline" onClick={() => startEdit(w.entry_id, w)}>
                  Edit dates
                </button>
                {w.provenance === "RESUME_DERIVED" && (
                  <button
                    className="text-[11px] text-cyan hover:underline"
                    onClick={() => confirmAsIs(w.entry_id)}
                    disabled={busy === w.entry_id}
                  >
                    Confirm as-is
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProjectsSection({
  ownerId,
  profile,
  onSaved,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function confirmAsIs(entryId: string) {
    setBusy(entryId);
    setErr(null);
    try {
      const updated = await careerProfileApi.reviewProject(ownerId, entryId, {});
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to confirm project.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="hl-card p-5 flex flex-col gap-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Projects ({profile.projects.length})
      </div>
      {err && <div className="text-[11.5px] text-red">{err}</div>}
      {profile.projects.length === 0 && <span className="text-[11.5px] text-muted">No projects on file.</span>}
      {profile.projects.map((p) => (
        <div key={p.entry_id} className="border border-border rounded-md p-3 flex flex-col gap-1.5">
          <div className="flex items-center justify-between flex-wrap gap-1.5">
            <div className="text-[12.5px] font-semibold">{p.name}</div>
            <SourceBadge provenance={p.provenance} />
          </div>
          {p.description && <div className="text-[11.5px]">{p.description}</div>}
          {p.skills_used.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {p.skills_used.map((s) => (
                <span key={s} className="hl-badge hl-badge-info text-[10.5px]">
                  {s}
                </span>
              ))}
            </div>
          )}
          {p.provenance === "RESUME_DERIVED" && (
            <button
              className="text-[11px] text-cyan hover:underline self-start"
              onClick={() => confirmAsIs(p.entry_id)}
              disabled={busy === p.entry_id}
            >
              {busy === p.entry_id ? "Confirming…" : "Confirm as-is"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function EducationSection({
  ownerId,
  profile,
  onSaved,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function confirmAsIs(entryId: string) {
    setBusy(entryId);
    setErr(null);
    try {
      const updated = await careerProfileApi.reviewEducation(ownerId, entryId, {});
      onSaved(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to confirm education.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="hl-card p-5 flex flex-col gap-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Education ({profile.education.length})
      </div>
      {err && <div className="text-[11.5px] text-red">{err}</div>}
      {profile.education.length === 0 && <span className="text-[11.5px] text-muted">No education on file.</span>}
      {profile.education.map((e) => (
        <div key={e.entry_id} className="border border-border rounded-md p-3 flex flex-col gap-1.5">
          <div className="flex items-center justify-between flex-wrap gap-1.5">
            <div className="text-[12.5px] font-semibold">
              {e.degree || "Degree"} <span className="text-muted font-normal">— {e.institution}</span>
            </div>
            <SourceBadge provenance={e.provenance} />
          </div>
          <div className="text-[11.5px] text-muted">
            {e.field_of_study ? `${e.field_of_study} · ` : ""}
            {e.start_date || "?"} — {e.end_date || "?"}
          </div>
          {e.provenance === "RESUME_DERIVED" && (
            <button
              className="text-[11px] text-cyan hover:underline self-start"
              onClick={() => confirmAsIs(e.entry_id)}
              disabled={busy === e.entry_id}
            >
              {busy === e.entry_id ? "Confirming…" : "Confirm as-is"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function CertificationsSection({ profile }: { profile: CareerProfile }) {
  return (
    <div className="hl-card p-5 flex flex-col gap-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Certifications ({profile.certifications.length})
      </div>
      {profile.certifications.length === 0 && (
        <span className="text-[11.5px] text-muted">No certifications on file.</span>
      )}
      {profile.certifications.map((c) => (
        <div key={c.entry_id} className="flex items-center flex-wrap gap-2 text-[12px]">
          <span className="font-semibold">{c.name}</span>
          {c.issuer && <span className="text-muted">· {c.issuer}</span>}
          {c.date && <span className="text-muted">· {c.date}</span>}
          <SourceBadge provenance={c.provenance} />
        </div>
      ))}
    </div>
  );
}

function LanguagesSection({ profile }: { profile: CareerProfile }) {
  if (profile.languages.length === 0) return null;
  return (
    <div className="hl-card p-5 flex flex-col gap-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">
        Languages ({profile.languages.length})
      </div>
      <div className="flex flex-wrap gap-2">
        {profile.languages.map((l) => (
          <span key={l.name} className="hl-badge hl-badge-info text-[11.5px]">
            {l.name}
            {l.proficiency ? ` · ${l.proficiency}` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

function ExtractionWarningsSection({ profile }: { profile: CareerProfile }) {
  const warnings = profile.resume_source.extraction_warnings;
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="hl-card p-5 flex flex-col gap-2 border-amber/40">
      <div className="text-[11px] font-bold uppercase tracking-wide text-amber">
        Extraction Warnings ({warnings.length})
      </div>
      <div className="text-[11px] text-muted">
        From the resume parser/validation pass that produced this profile — reused verbatim, nothing reworded.
      </div>
      <ul className="text-[11.5px] text-text list-disc list-inside space-y-0.5">
        {warnings.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </div>
  );
}

function DiffSection({ title, items, kind }: { title: string; items: string[]; kind: "success" | "warning" }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className={`text-[11px] font-bold uppercase tracking-wide mb-1 ${kind === "success" ? "text-green" : "text-amber"}`}>
        {title} ({items.length})
      </div>
      <ul className="text-[11.5px] text-text list-disc list-inside">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function OptionalTab({
  ownerId,
  profile,
  onSaved,
  onDirtyChange,
  onRegisterSave,
}: {
  ownerId: string;
  profile: CareerProfile;
  onSaved: (p: CareerProfile) => void;
} & DirtyTrackedTabProps) {
  const d = profile.demographics;
  const [form, setForm] = useState({
    gender: d.gender,
    race_ethnicity: d.race_ethnicity,
    veteran_status: d.veteran_status,
    disability_status: d.disability_status,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { markClean } = useDirtyForm(form, onDirtyChange);

  async function save(): Promise<boolean> {
    setSaving(true);
    setErr(null);
    try {
      const updated = await careerProfileApi.updateDemographics(ownerId, form);
      onSaved(updated);
      markClean();
      return true;
    } catch (e) {
      setErr(errorMessage(e, "Failed to save demographics."));
      return false;
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    onRegisterSave?.(async () => {
      if (!(await save())) throw new Error("Save failed. See the error shown on this tab.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  return (
    <div className="flex flex-col gap-4">
      <div className="hl-card p-5 flex flex-col gap-3 max-w-[640px]">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">EEO / Demographics (optional)</div>
        <div className="text-[11.5px] text-muted">
          Entirely optional and self-reported. Defaults to &quot;Not Provided&quot;. Never read by scoring, ranking,
          or the learning loop — structurally excluded from those code paths.
        </div>
        <div className="grid grid-cols-2 gap-3">
          {(["gender", "race_ethnicity", "veteran_status", "disability_status"] as const).map((f) => (
            <label key={f} className="flex flex-col gap-1 text-[11.5px]">
              <span className="text-muted font-semibold">{f.replace("_", " ")}</span>
              <input className="hl-input" value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
            </label>
          ))}
        </div>
        <SaveBar onSave={save} saving={saving} error={err} />
      </div>

      <div className="hl-card p-5 flex flex-col gap-2 max-w-[640px]">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">References (optional)</div>
        <div className="text-[11.5px] text-muted">
          {profile.references.length === 0
            ? "No references on file. Never required for any part of HireLoop."
            : `${profile.references.length} reference(s) on file.`}
        </div>
      </div>
    </div>
  );
}
