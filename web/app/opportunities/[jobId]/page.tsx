"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Badge from "@/components/Badge";
import ScoreRing from "@/components/ScoreRing";
import ScoreBar from "@/components/ScoreBar";
import HumanDecisionModal from "@/components/HumanDecisionModal";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { OpportunityDetail } from "@/lib/types";

const CERTIFICATION_DEMO_JOB_ID = "job_ai_001";

function label(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function OpportunityDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = decodeURIComponent(params.jobId);
  const router = useRouter();
  const { sessionId, mc, applyResume, loading: acting } = useSession();
  const [detail, setDetail] = useState<OpportunityDetail | null | undefined>(undefined);
  const [showSelectModal, setShowSelectModal] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    api
      .opportunityDetail(sessionId, jobId)
      .then(setDetail)
      .catch(() => setDetail(null));
    // Re-fetch whenever mission control state changes (e.g. after a
    // SELECT resumes the workflow) so this page never shows stale data.
  }, [sessionId, jobId, mc]);

  if (detail === undefined) {
    return <div className="text-muted text-[13px] px-1 py-10">Loading opportunity intelligence…</div>;
  }

  if (detail === null) {
    return (
      <div className="hl-card p-8 max-w-lg text-center flex flex-col gap-3">
        <p className="text-[13px] text-muted">
          This opportunity hasn&apos;t been scored in the current session yet.
        </p>
        <Link href="/opportunities" className="hl-btn-secondary self-center">
          Back to Opportunities
        </Link>
      </div>
    );
  }

  const isEligibleNow = Boolean(
    mc?.interrupt?.eligible_selections?.some((s) => s.job_id === detail.job_id)
  );
  const isDemoPick = detail.job_id === CERTIFICATION_DEMO_JOB_ID;

  return (
    <div className="flex flex-col gap-5 max-w-[1200px]">
      {/* Breadcrumb */}
      <div className="text-[12px] text-muted flex items-center gap-1.5">
        <Link href="/opportunities" className="hover:text-cyan">
          Opportunities
        </Link>
        <span>/</span>
        <span className="text-text">{detail.title}</span>
      </div>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-extrabold tracking-tight">{detail.title}</h1>
            {isDemoPick && (
              <span
                className="hl-badge hl-badge-violet"
                title="Selected to demonstrate both supported and unsupported resume evidence."
              >
                CERTIFICATION DEMO PICK
              </span>
            )}
          </div>
          <p className="text-[13px] text-muted mt-1">
            {detail.company} · {detail.location}
            {detail.work_mode ? ` · ${detail.work_mode}` : ""}
          </p>
        </div>
        {isEligibleNow && (
          <button
            className="hl-btn-primary"
            disabled={acting}
            onClick={() => setShowSelectModal(true)}
          >
            Select Opportunity
          </button>
        )}
      </div>

      {/* Score header */}
      <div className="hl-card p-6 flex flex-wrap items-center gap-6">
        <ScoreRing value={detail.score} size={116} />
        <div className="flex flex-col gap-1.5">
          <div className="text-[13px]">
            <span className="font-semibold">Recommendation: </span>
            <Badge label={detail.recommendation} kind="info" />
          </div>
          <div className="text-[13px] flex items-center gap-2">
            <span className="font-semibold">Score confidence:</span> <Badge label={detail.confidence} />
          </div>
          {detail.listing_confidence && (
            <div className="text-[13px] flex items-center gap-2">
              <span className="font-semibold">Listing confidence:</span> <Badge label={detail.listing_confidence} />
            </div>
          )}
          <div className="text-[11px] text-muted mt-1">Scoring model: {detail.scoring_version ?? "unknown"}</div>
        </div>
      </div>

      {/* Opportunity DNA */}
      {Object.keys(detail.components).length > 0 && (
        <div className="hl-card p-6">
          <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-1">Opportunity DNA</div>
          <p className="text-[11px] text-muted mb-4">
            The 7 deterministic components behind the score above — computed once by the Opportunity Scoring
            Engine, never recomputed in this UI.
          </p>
          <div className="flex flex-col gap-3">
            {Object.entries(detail.components).map(([name, comp]) => (
              <ScoreBar
                key={name}
                label={label(name)}
                value={comp.value}
                weight={comp.weight}
                contribution={comp.weighted_contribution}
              />
            ))}
          </div>
        </div>
      )}

      {/* Why this fits / watch out for */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="hl-card p-5">
          <div className="text-[11px] font-bold uppercase tracking-wide text-green mb-2">Why This Fits</div>
          {detail.strengths.length > 0 ? (
            <ul className="list-disc list-inside text-[12.5px] text-muted space-y-1">
              {detail.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-muted">No strengths recorded by Match Analyst for this opportunity.</p>
          )}
        </div>
        <div className="hl-card p-5">
          <div className="text-[11px] font-bold uppercase tracking-wide text-amber mb-2">Watch Out For</div>
          {[...detail.gaps, ...detail.risks].length > 0 ? (
            <ul className="list-disc list-inside text-[12.5px] text-muted space-y-1">
              {[...detail.gaps, ...detail.risks].map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-muted">No gaps or risks recorded by Match Analyst for this opportunity.</p>
          )}
        </div>
      </div>

      {detail.explanation && (
        <div className="hl-card p-5">
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Match Analyst Explanation</div>
          <p className="text-[12.5px]">{detail.explanation}</p>
        </div>
      )}

      {/* Behind the decision */}
      <div className="hl-card p-6">
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-3">Behind The Decision</div>
        <div className="flex items-center gap-2 flex-wrap text-[12px]">
          <FunnelStep label="Discovered" value={detail.funnel.discovered} />
          <Arrow />
          <FunnelStep label="Unique" value={detail.funnel.unique_after_dedup} />
          <Arrow />
          <FunnelStep label="Scored" value={detail.funnel.scored} />
          <Arrow />
          <FunnelStep label="Analyzed" value={detail.funnel.analyzed} />
          <Arrow />
          <FunnelStep label="This Job" value={`${detail.score.toFixed(0)} · ${detail.recommendation}`} highlight />
        </div>
        <p className="text-[11.5px] text-muted mt-4">
          The score is calculated deterministically. Match Analyst explains it but cannot change it.
        </p>
      </div>

      {isEligibleNow && showSelectModal && (
        <HumanDecisionModal
          completed={[
            "HireLoop scored and analyzed every eligible opportunity from this search.",
            `${detail.title} at ${detail.company} is eligible for selection right now.`,
          ]}
          decision="Whether to pursue this opportunity next."
          why="HireLoop never applies on your behalf — selecting a target opportunity is a consequential decision reserved for a human."
          onDismiss={() => setShowSelectModal(false)}
        >
          <div className="flex gap-2 flex-wrap mt-1">
            <button
              className="hl-btn-primary"
              disabled={acting}
              onClick={async () => {
                await applyResume({ action: "SELECT", job_id: detail.job_id });
                setShowSelectModal(false);
                router.push("/resume-studio");
              }}
            >
              Select {detail.title} @ {detail.company}
            </button>
          </div>
        </HumanDecisionModal>
      )}
    </div>
  );
}

function FunnelStep({ label, value, highlight = false }: { label: string; value: number | string; highlight?: boolean }) {
  return (
    <div
      className="rounded-lg px-3 py-2 flex flex-col items-center min-w-[92px]"
      style={{
        background: highlight ? "rgba(139,92,246,.14)" : "var(--card-alt)",
        border: `1px solid ${highlight ? "rgba(139,92,246,.4)" : "var(--border)"}`,
      }}
    >
      <div className="font-extrabold tabular-nums text-[13px]">{value}</div>
      <div className="text-[10px] text-muted uppercase tracking-wide">{label}</div>
    </div>
  );
}

function Arrow() {
  return <span className="text-muted">→</span>;
}
