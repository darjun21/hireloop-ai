"use client";

import { useEffect, useState } from "react";
import Badge from "@/components/Badge";
import HumanDecisionBanner from "@/components/HumanDecisionBanner";
import HumanDecisionModal from "@/components/HumanDecisionModal";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { ResumeStudioView } from "@/lib/types";

export default function ResumeStudioPage() {
  const { sessionId, mc, applyResume, loading } = useSession();
  const [view, setView] = useState<ResumeStudioView | null>(null);
  const [detail, setDetail] = useState("");
  const [approvalModalDismissed, setApprovalModalDismissed] = useState(false);
  const [clarificationModalDismissed, setClarificationModalDismissed] = useState(false);
  const [selectedModIds, setSelectedModIds] = useState<string[]>([]);

  useEffect(() => {
    if (!sessionId) return;
    api.resumeStudio(sessionId).then(setView).catch(() => setView(null));
  }, [sessionId, mc]);

  useEffect(() => {
    // Resets local selection/dismiss state whenever the backend interrupt payload
    // changes (a new set of modifications to review) -- not synchronizing with an
    // external system on every render, only when the interrupt identity changes.
    if (view?.interrupt?.modifications) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- see comment above
      setSelectedModIds(view.interrupt.modifications.map((m) => m.modification_id));
      setApprovalModalDismissed(false);
    }
    if (view?.interrupt?.clarification_required) {
      setClarificationModalDismissed(false);
    }
  }, [view?.interrupt]);

  if (!view) return <div className="text-muted text-[13px] px-1 py-10">Loading Resume Studio…</div>;

  if (!view.selected_job_id) {
    return (
      <div className="hl-card p-8 max-w-lg text-center">
        <p className="text-[13px] text-muted">No opportunity selected yet. Select one from Opportunities first.</p>
      </div>
    );
  }

  const interrupt = view.interrupt;

  return (
    <div className="flex flex-col gap-5 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Resume Studio</h1>
        <p className="text-[12.5px] text-muted mt-0.5">Tailored for relevance. Guarded by evidence.</p>
      </div>

      <div className="hl-card p-5">
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-3">Truth Guard Summary</div>
        <div className="grid grid-cols-4 gap-3 text-center">
          <Stat label="Verified" value={view.counts.VERIFIED} color="var(--green)" />
          <Stat label="Partially Supported" value={view.counts.PARTIALLY_SUPPORTED} color="var(--amber)" />
          <Stat label="Blocked" value={view.counts.UNSUPPORTED} color="var(--red)" />
          <Stat label="Needs Confirmation" value={view.counts.NEEDS_HUMAN_CONFIRMATION} color="var(--violet)" />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted">Proposed Modifications</div>
        {view.modifications.map((mod) => (
          <div key={mod.modification_id} className="hl-card p-4 flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <Badge label={mod.status_label} />
            </div>
            <div className="text-[12px]">
              <span className="font-semibold">Section: </span>
              {mod.section}
            </div>
            {mod.original_text && (
              <div className="text-[12px] text-muted line-through decoration-red">{mod.original_text}</div>
            )}
            <div className="text-[12px]">{mod.proposed_text}</div>
            <p className="text-[11px] text-muted">Why: {mod.reason}</p>
            <p className="text-[11px] text-muted">Evidence: {mod.evidence_ids.join(", ") || "none"}</p>
            {mod.status !== "VERIFIED" && mod.explanation && (
              <p className="text-[11px] text-amber">Truth Guard: {mod.explanation}</p>
            )}
          </div>
        ))}

        {view.rejected.length > 0 && (
          <div>
            <div className="text-[12px] font-semibold mb-1">Removed (unsupported, could not be corrected)</div>
            {view.rejected.map((r) => (
              <div key={r.modification_id} className="text-[12px] flex items-center gap-2">
                <Badge label="UNSUPPORTED" kind="danger" />
                <span className="line-through text-muted">{r.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {interrupt?.clarification_required && (
        <>
          <HumanDecisionBanner
            completed={["Truth Guard checked this claim against retrieved evidence and could not confirm or reject it automatically."]}
            decision="Whether this claim is accurate, should use a safe rewrite instead, or should be rejected."
            why="The evidence is insufficient for Truth Guard to decide on its own — accepting or rejecting an unverifiable claim about your background is a human call."
          />
          <div className="hl-card p-4 flex flex-col gap-2">
            <div className="text-[12px]">
              <span className="font-semibold">Claim: </span>
              {interrupt.clarification_required.proposed_claim}
            </div>
            <div className="text-[12px] text-muted">{interrupt.clarification_required.explanation}</div>
            <input
              className="hl-card px-3 py-2 text-[12px] bg-card-alt"
              placeholder="Confirmation detail (if confirming)"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
            />
            <div className="flex gap-2 flex-wrap">
              <button
                className="hl-btn-primary"
                disabled={loading}
                onClick={() => applyResume({ action: "CONFIRM_WITH_EVIDENCE", confirmation_detail: detail || "Human confirmed this claim is accurate." })}
              >
                Confirm with evidence
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "USE_SAFE_REWRITE" })}>
                Use safe rewrite
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "REJECT_CLAIM" })}>
                Reject
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "CANCEL" })}>
                Cancel
              </button>
            </div>
          </div>
        </>
      )}

      {interrupt?.modifications && (
        <>
          <HumanDecisionBanner
            completed={[
              `Truth Guard verified ${view.counts.VERIFIED} modification(s) as fully supported by your real resume/experience.`,
              `${view.rejected.length} unsupported modification(s) were already blocked and will never reach your resume.`,
            ]}
            decision="Which of the verified modifications to actually apply to your resume."
            why="Even fully verified changes only go live on a human's approval — HireLoop never edits your resume unattended."
          />
          <div className="flex gap-2 flex-wrap">
            <button className="hl-btn-primary" disabled={loading} onClick={() => applyResume({ action: "APPROVE_ALL" })}>
              Approve all safe changes
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "REJECT_ALL" })}>
              Reject all
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "CANCEL" })}>
              Cancel
            </button>
          </div>
        </>
      )}

      {interrupt?.clarification_required && !clarificationModalDismissed && (
        <HumanDecisionModal
          title="Evidence Clarification Required"
          subtitle="Truth Guard checked this claim against retrieved evidence and could not confirm or reject it automatically."
          completed={["Truth Guard searched the candidate's evidence pool for support of this claim."]}
          decision="Whether this claim is accurate, should use a safe rewrite instead, or should be rejected."
          why="The evidence is insufficient for Truth Guard to decide on its own — accepting or rejecting an unverifiable claim about your background is a human call. Never marked VERIFIED without a real human decision."
          onDismiss={() => setClarificationModalDismissed(true)}
          maxWidth={640}
        >
          <div className="flex flex-col gap-2 mt-1">
            <div className="text-[12px]">
              <span className="font-semibold">Proposed claim: </span>
              {interrupt.clarification_required.proposed_claim}
            </div>
            <div className="text-[12px] text-muted">
              <span className="font-semibold text-text">Why insufficient: </span>
              {interrupt.clarification_required.explanation}
            </div>
            {interrupt.clarification_required.closest_evidence_ids && interrupt.clarification_required.closest_evidence_ids.length > 0 && (
              <div className="text-[12px] text-muted">
                <span className="font-semibold text-text">Closest evidence: </span>
                {interrupt.clarification_required.closest_evidence_ids.join(", ")}
              </div>
            )}
            {interrupt.clarification_required.safe_option && (
              <div className="text-[12px] text-muted">
                <span className="font-semibold text-text">Safe rewrite available: </span>
                {interrupt.clarification_required.safe_option}
              </div>
            )}
            <input
              className="hl-card px-3 py-2 text-[12px] bg-card-alt mt-1"
              placeholder="Confirmation detail (required to confirm with evidence)"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
            />
            <div className="flex gap-2 flex-wrap mt-1">
              <button
                className="hl-btn-primary"
                disabled={loading}
                onClick={() =>
                  applyResume({ action: "CONFIRM_WITH_EVIDENCE", confirmation_detail: detail || "Human confirmed this claim is accurate." })
                }
              >
                Confirm With Evidence
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "USE_SAFE_REWRITE" })}>
                Use Safe Rewrite
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "REJECT_CLAIM" })}>
                Reject Claim
              </button>
              <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "CANCEL" })}>
                Cancel
              </button>
            </div>
          </div>
        </HumanDecisionModal>
      )}

      {interrupt?.modifications && !approvalModalDismissed && (
        <HumanDecisionModal
          title="Review evidence-grounded resume changes"
          subtitle="HireLoop has finished tailoring and verification. Only the changes you approve can enter the new resume version."
          completed={[
            `Truth Guard verified ${view.counts.VERIFIED} modification(s) as fully supported by your real resume/experience.`,
            `${view.rejected.length} unsupported modification(s) were already blocked and will never reach your resume.`,
          ]}
          decision="Which of the verified modifications to actually apply to your resume."
          why="Even fully verified changes only go live on a human's approval — HireLoop never edits your resume unattended."
          onDismiss={() => setApprovalModalDismissed(true)}
          maxWidth={640}
        >
          <div className="grid grid-cols-4 gap-2 text-center mt-1">
            <Stat label="Verified" value={view.counts.VERIFIED} color="var(--green)" />
            <Stat label="Partial" value={view.counts.PARTIALLY_SUPPORTED} color="var(--amber)" />
            <Stat label="Blocked" value={view.counts.UNSUPPORTED} color="var(--red)" />
            <Stat label="Needs Confirmation" value={view.counts.NEEDS_HUMAN_CONFIRMATION} color="var(--violet)" />
          </div>

          <div className="flex flex-col gap-1.5 mt-2 max-h-[240px] overflow-y-auto">
            {interrupt.modifications.map((m) => {
              const mid = m.modification_id;
              const proposed = typeof m.proposed === "string" ? m.proposed : "";
              const checked = selectedModIds.includes(mid);
              return (
                <label key={mid} className="flex items-start gap-2 text-[11.5px] rounded-md px-2 py-1.5" style={{ background: "var(--card-alt)" }}>
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={checked}
                    onChange={(e) =>
                      setSelectedModIds((prev) => (e.target.checked ? [...prev, mid] : prev.filter((id) => id !== mid)))
                    }
                  />
                  <span>
                    <Badge label="VERIFIED" /> {proposed}
                  </span>
                </label>
              );
            })}
          </div>

          <div className="flex gap-2 flex-wrap mt-3">
            <button className="hl-btn-primary" disabled={loading} onClick={() => applyResume({ action: "APPROVE_ALL" })}>
              Approve Safe Changes
            </button>
            <button
              className="hl-btn-secondary"
              disabled={loading || selectedModIds.length === 0}
              onClick={() => applyResume({ action: "APPROVE_SELECTED", modification_ids: selectedModIds })}
            >
              Approve Selected
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "REJECT_ALL" })}>
              Reject All
            </button>
            <button className="hl-btn-secondary" disabled={loading} onClick={() => applyResume({ action: "CANCEL" })}>
              Cancel
            </button>
          </div>
        </HumanDecisionModal>
      )}

      {view.current_resume_version_id && !interrupt && (
        <div className="hl-card p-4">
          <Badge label="RESUME VERSION CREATED" kind="success" />
          <p className="text-[12px] mt-2">Version ID: {view.current_resume_version_id}</p>
          <p className="text-[12px]">Approved changes: {view.approved_modification_ids.length}</p>
          <p className="text-[11px] text-muted mt-1">Original Resume Preserved — the parsed resume text was never modified.</p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="text-xl font-extrabold tabular-nums" style={{ color }}>
        {value}
      </div>
      <div className="text-[10px] text-muted">{label}</div>
    </div>
  );
}
