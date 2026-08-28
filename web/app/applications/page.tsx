"use client";

import { useEffect, useState } from "react";
import Badge from "@/components/Badge";
import HumanDecisionBanner from "@/components/HumanDecisionBanner";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { ApplicationsView } from "@/lib/types";

const PIPELINE = ["SAVED", "APPLIED", "RESPONSE", "INTERVIEW", "FINAL ROUND", "OFFER"];

export default function ApplicationsPage() {
  const { sessionId, mc, applyResume, loading } = useSession();
  const [view, setView] = useState<ApplicationsView | null>(null);

  const load = () => {
    if (!sessionId) return;
    api.applications(sessionId).then(setView).catch(() => setView(null));
  };

  useEffect(load, [sessionId, mc]);

  if (!view) return <div className="text-muted text-[13px] px-1 py-10">Loading Applications…</div>;

  return (
    <div className="flex flex-col gap-5 max-w-[1200px]">
      <h1 className="text-2xl font-extrabold tracking-tight">Applications</h1>

      {view.pending_application_interrupt && (
        <>
          <HumanDecisionBanner
            completed={[`HireLoop created a tracked application record for job ${view.pending_application_interrupt.job_id} with a verified, approved resume.`]}
            decision="Whether — and how — to record this application (applied, saved for later, or cancel)."
            why="HireLoop never submits an application automatically; marking something as applied is a real-world action only you can confirm actually happened."
          />
          <div className="flex gap-2">
            <button className="hl-btn-primary" disabled={loading} onClick={() => applyResume({ action: "MARK_APPLIED" }).then(load)}>
              Mark Applied
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "SAVE_FOR_LATER" }).then(load)}>
              Save for later
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "CANCEL" }).then(load)}>
              Cancel
            </button>
          </div>
        </>
      )}

      <div className="text-[13px] font-bold uppercase tracking-wider text-muted">Tracked Applications</div>
      {view.applications.length === 0 && <p className="text-[12.5px] text-muted">No applications tracked yet.</p>}

      {view.applications.map(({ application, history }) => {
        const normalized = application.current_status.toUpperCase().replace(/_/g, " ");
        return (
          <div key={application.application_id} className="hl-card p-4 flex flex-col gap-2.5">
            <div className="flex gap-1">
              {PIPELINE.map((step) => (
                <div
                  key={step}
                  className="flex-1 h-1.5 rounded-full"
                  style={{
                    background: step === normalized || normalized.includes(step) ? "linear-gradient(90deg,#20C8FF,#8B5CF6)" : "var(--card-alt)",
                  }}
                  title={step}
                />
              ))}
            </div>
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <div className="font-semibold text-[13px]">
                  {application.title || application.job_id}
                  {application.company ? ` @ ${application.company}` : ""}
                </div>
                <div className="text-[11px] text-muted">
                  {application.job_id} · Role family: {application.role_family || "—"}
                </div>
              </div>
              <div className="text-[12px] tabular-nums">
                Score: {application.opportunity_score?.toFixed(1) ?? "—"}
              </div>
              <Badge label={application.current_status} kind="neutral" />
              <div className="text-[11px] text-muted">Resume: {application.selected_resume_version_id || "—"}</div>
            </div>
            <div className="text-[11px] text-muted">
              Applied: {application.applied_at || "not yet"} · Latest event: {history[history.length - 1]?.event_type || "—"}
            </div>
            <OutcomeRecorder applicationId={application.application_id} onDone={load} />
          </div>
        );
      })}
    </div>
  );
}

function OutcomeRecorder({ applicationId, onDone }: { applicationId: string; onDone: () => void }) {
  const { sessionId } = useSession();
  const [interrupt, setInterrupt] = useState<Record<string, unknown> | null | undefined>(undefined);
  const [choice, setChoice] = useState<string>("");

  const start = async () => {
    if (!sessionId) return;
    const res = await api.outcomeStart(sessionId, applicationId);
    const data = res as { interrupt: Record<string, unknown> | null };
    setInterrupt(data.interrupt);
    const actions = (data.interrupt?.allowed_actions as string[] | undefined) || [];
    setChoice(actions.find((a) => a !== "CANCEL") || "");
  };

  const submit = async () => {
    if (!sessionId || !choice) return;
    const res = await api.outcomeSubmit(sessionId, applicationId, { action: choice });
    const data = res as { interrupt: Record<string, unknown> | null };
    setInterrupt(data.interrupt);
    if (!data.interrupt) onDone();
  };

  if (interrupt === undefined) {
    return (
      <button className="hl-btn-secondary self-start" onClick={start}>
        Start outcome update
      </button>
    );
  }
  if (interrupt === null) {
    return <p className="text-[11px] text-green">Outcome workflow completed for this application.</p>;
  }

  const actions = ((interrupt.allowed_actions as string[] | undefined) || []).filter((a) => a !== "CANCEL");
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select className="hl-card px-2 py-1.5 text-[12px] bg-card-alt" value={choice} onChange={(e) => setChoice(e.target.value)}>
        {actions.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <button className="hl-btn-primary" onClick={submit}>
        Submit outcome
      </button>
    </div>
  );
}
