"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/Icon";
import KpiRow from "@/components/KpiRow";
import HumanLoopDiagram from "@/components/HumanLoopDiagram";
import TopOpportunityCard from "@/components/TopOpportunityCard";
import InsightCard from "@/components/InsightCard";
import AgentActivityRail from "@/components/AgentActivityRail";
import TruthGuardCard from "@/components/TruthGuardCard";
import RecentActivity from "@/components/RecentActivity";
import HumanDecisionBanner from "@/components/HumanDecisionBanner";
import HumanDecisionModal from "@/components/HumanDecisionModal";
import { useSession } from "@/lib/session-context";
import { careerProfileApi, getOwnerId } from "@/lib/career-profile-api";

export default function MissionControlPage() {
  const { mc, mode, loading, error, startDemo, applyResume } = useSession();
  const [modalDismissed, setModalDismissed] = useState(false);

  // Only used for the PERSONAL-mode empty state's primary CTA (Complete
  // Career Profile vs. Find Opportunities) -- read-only, never affects the
  // server-side confirmation gate itself (api/main.py::start_run remains
  // the actual enforcement point).
  const [confirmedAt, setConfirmedAt] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (mode !== "PERSONAL" || (mc && mc.has_run)) return;
    let cancelled = false;
    careerProfileApi
      .getOrCreate(getOwnerId())
      .then((profile) => {
        if (!cancelled) setConfirmedAt(profile.confirmed_at);
      })
      .catch(() => {
        if (!cancelled) setConfirmedAt(null);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, mc]);

  if (error) {
    return (
      <div className="hl-card p-6 max-w-xl mx-auto mt-10">
        <div className="font-bold mb-2 text-red">Could not reach the API bridge</div>
        <p className="text-[12.5px] text-muted">{error}</p>
        <p className="text-[12px] text-muted mt-2">
          Start it with: <code className="text-cyan">uvicorn api.main:app --reload --port 8000</code>
        </p>
      </div>
    );
  }

  if (loading && !mc) {
    return <div className="text-muted text-[13px] px-1 py-10">Loading Mission Control…</div>;
  }

  if (!mc) return null;

  const greetingName = mc.candidate_first_name;

  return (
    <div className="flex flex-col gap-2.5 max-w-[1760px]">
      <div>
        <h1 className="text-[22px] font-extrabold tracking-tight leading-tight">
          {greetingName
            ? `Good afternoon, ${greetingName}.`
            : mode === "CERTIFICATION_DEMO"
              ? "HireLoop Certification Demo"
              : "Welcome back."}
        </h1>
        <p className="text-[12px] text-muted mt-0.5">
          {greetingName
            ? "Your next opportunity is taking shape."
            : mode === "CERTIFICATION_DEMO"
              ? "Synthetic data only — this run never touches your real Career Profile."
              : "Ready for your next loop."}
        </p>
      </div>

      {!mc.has_run ? (
        mode === "CERTIFICATION_DEMO" ? (
          <div className="hl-card p-8 flex flex-col items-center text-center gap-3 max-w-2xl">
            <Icon name="bolt" size={26} color="var(--violet)" />
            <div className="text-lg font-bold">HireLoop Certification Demo</div>
            <p className="text-[13px] text-muted max-w-md">
              Synthetic data only. See live discovery, scoring, matching, and Truth Guard verification — driven by
              the real HireLoop backend, using a seeded synthetic candidate.
            </p>
            <button className="hl-btn-primary mt-2" onClick={() => startDemo()} disabled={loading}>
              {loading ? "Starting…" : "START CERTIFICATION DEMO"}
            </button>
          </div>
        ) : (
          <div className="hl-card p-8 flex flex-col items-center text-center gap-4 max-w-2xl">
            <Icon name="bolt" size={26} color="var(--cyan)" />
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-1">Welcome Back</div>
              <div className="text-lg font-bold">Ready for Your Next Loop</div>
            </div>
            <p className="text-[13px] text-muted max-w-md">
              Complete your Career Profile and discover opportunities matched to your experience, goals, and
              preferences.
            </p>
            {confirmedAt === undefined ? null : confirmedAt ? (
              <Link href="/candidate-setup" className="hl-btn-primary mt-1">
                FIND OPPORTUNITIES
              </Link>
            ) : (
              <Link href="/career-profile" className="hl-btn-primary mt-1">
                COMPLETE CAREER PROFILE
              </Link>
            )}

            <div className="w-full max-w-sm border-t border-[var(--border)] mt-2 pt-4 flex flex-col items-center gap-2">
              <p className="text-[12px] text-muted">Want to explore the full workflow instantly?</p>
              <button
                className="hl-btn-secondary text-[12px]"
                onClick={() => startDemo()}
                disabled={loading}
              >
                {loading ? "Starting…" : "TRY CERTIFICATION DEMO"}
              </button>
              <p className="text-[11px] text-muted">Synthetic data only. Your Personal Career Profile will not be used.</p>
            </div>
          </div>
        )
      ) : (
        <>
          <KpiRow items={mc.kpis} />

          <div className="hl-card p-2.5 pb-0">
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-0">The HireLoop</div>
            <HumanLoopDiagram stageStatus={mc.stage_status} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr_320px] gap-2.5 items-start">
            <div className="xl:col-span-2 grid grid-cols-1 lg:grid-cols-2 gap-3">
              {mc.top_opportunity ? (
                <TopOpportunityCard opp={mc.top_opportunity} />
              ) : (
                <div className="hl-card p-5 text-[12.5px] text-muted">No opportunities scored yet.</div>
              )}
              <InsightCard insight={mc.latest_insight} />
            </div>
            <div className="flex flex-col gap-3">
              <AgentActivityRail
                rows={mc.agent_activity}
                dense={mc.truth_guard_summary.counts.verified + mc.truth_guard_summary.counts.blocked + mc.truth_guard_summary.counts.review > 0}
              />
              <TruthGuardCard summary={mc.truth_guard_summary} />
            </div>
          </div>

          {mc.interrupt?.eligible_selections && (
            <HumanDecisionBanner
              completed={[
                "HireLoop scored and analyzed every eligible opportunity from this search.",
                `${mc.interrupt.eligible_selections.length} opportunity(ies) are eligible for selection right now.`,
              ]}
              decision="Which opportunity (if any) to pursue next."
              why="HireLoop never applies on your behalf — selecting a target opportunity is a consequential decision reserved for a human."
            />
          )}

          <RecentActivity events={mc.recent_activity} />

          {mc.interrupt?.eligible_selections && !modalDismissed && (
            <HumanDecisionModal
              completed={[
                "HireLoop scored and analyzed every eligible opportunity from this search.",
                `${mc.interrupt.eligible_selections.length} opportunity(ies) are eligible for selection right now.`,
              ]}
              decision="Which opportunity (if any) to pursue next."
              why="HireLoop never applies on your behalf — selecting a target opportunity is a consequential decision reserved for a human."
              onDismiss={() => setModalDismissed(true)}
            >
              {mc.top_opportunity && (
                <button
                  className="hl-btn-primary self-start"
                  disabled={!mc.top_opportunity.selectable || loading}
                  onClick={() => applyResume({ action: "SELECT", job_id: mc.top_opportunity!.job_id })}
                >
                  Select {mc.top_opportunity.title} @ {mc.top_opportunity.company}
                </button>
              )}
            </HumanDecisionModal>
          )}
        </>
      )}
    </div>
  );
}
