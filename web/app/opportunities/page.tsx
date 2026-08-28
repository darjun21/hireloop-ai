"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Badge from "@/components/Badge";
import ScoreRing from "@/components/ScoreRing";
import ScoreBar from "@/components/ScoreBar";
import HumanDecisionBanner from "@/components/HumanDecisionBanner";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { OpportunitiesView, OpportunityRow } from "@/lib/types";

const CERTIFICATION_DEMO_JOB_ID = "job_ai_001";

function OpportunitiesInner() {
  const { sessionId, mc, applyResume, loading: acting } = useSession();
  const searchParams = useSearchParams();
  const [view, setView] = useState<OpportunitiesView | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("job"));
  const [recFilter, setRecFilter] = useState("All");
  const [minScore, setMinScore] = useState(0);

  useEffect(() => {
    if (!sessionId) return;
    api.opportunities(sessionId).then(setView).catch(() => setView(null));
  }, [sessionId, mc]);

  const rows = useMemo(() => {
    if (!view) return [];
    return view.opportunities.filter((o) => {
      if (recFilter !== "All" && o.recommendation !== recFilter) return false;
      if (o.score < minScore) return false;
      return true;
    });
  }, [view, recFilter, minScore]);

  if (!view) return <div className="text-muted text-[13px] px-1 py-10">Loading opportunities…</div>;

  if (view.opportunities.length === 0) {
    return (
      <div className="hl-card p-8 max-w-lg text-center">
        <p className="text-[13px] text-muted">No opportunities yet. Start the certification demo from Mission Control.</p>
      </div>
    );
  }

  const detail = rows.find((r) => r.job_id === selectedId) || view.opportunities.find((r) => r.job_id === selectedId);

  return (
    <div className="flex flex-col gap-5 max-w-[1600px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Opportunities</h1>
        <p className="text-[12.5px] text-muted mt-0.5">
          {view.counts.ingested ?? "—"} discovered · {view.counts.unique_after_dedup ?? "—"} unique · {view.counts.scored ?? "—"} scored
        </p>
      </div>

      <div className="flex gap-3 items-center flex-wrap">
        <select
          className="hl-card px-3 py-2 text-[12px] bg-card"
          value={recFilter}
          onChange={(e) => setRecFilter(e.target.value)}
        >
          {["All", "HIGH_PRIORITY", "STRONG_MATCH", "CONSIDER", "LOW_PRIORITY"].map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <label className="text-[12px] text-muted flex items-center gap-2">
          Min score
          <input type="range" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
          <span className="tabular-nums">{minScore}</span>
        </label>
        <span className="text-[12px] text-muted ml-auto">{rows.length} shown, sorted by score</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {rows.map((o) => (
          <OpportunityCard key={o.job_id} o={o} onDetail={() => setSelectedId(o.job_id)} />
        ))}
      </div>

      {detail && (
        <div className="hl-card p-6 flex flex-col gap-5">
          <h2 className="text-lg font-bold">
            Opportunity Intelligence — {detail.title} at {detail.company}
          </h2>
          <div className="flex items-center gap-6">
            <ScoreRing value={detail.score} />
            <div>
              <div className="text-[12.5px]">
                <span className="font-semibold">Recommendation:</span> {detail.recommendation}
              </div>
              <div className="text-[12.5px] mt-1 flex items-center gap-2">
                <span className="font-semibold">Confidence:</span> <Badge label={detail.confidence} />
              </div>
              <div className="text-[11px] text-muted mt-1">Scoring model: {detail.scoring_version}</div>
            </div>
          </div>

          {Object.keys(detail.components).length > 0 && (
            <div>
              <div className="text-[12px] font-semibold mb-2">Opportunity DNA — the real components behind the score above</div>
              <div className="flex flex-col gap-2.5">
                {Object.entries(detail.components).map(([name, comp]) => (
                  <ScoreBar
                    key={name}
                    label={name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    value={comp.value}
                    weight={comp.weight}
                    contribution={comp.weighted_contribution}
                  />
                ))}
              </div>
            </div>
          )}

          {detail.explanation && (
            <div>
              <div className="text-[12px] font-semibold mb-1">Why This Fits</div>
              <p className="text-[12.5px] text-muted">{detail.explanation}</p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] font-bold uppercase text-green mb-1">Why This Fits</div>
              <ul className="list-disc list-inside text-[12px] text-muted space-y-1">
                {detail.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase text-amber mb-1">Watch Out For</div>
              <ul className="list-disc list-inside text-[12px] text-muted space-y-1">
                {[...detail.gaps, ...detail.risks].map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          </div>

          {mc?.interrupt?.eligible_selections?.some((s) => s.job_id === detail.job_id) ? (
            <>
              <HumanDecisionBanner
                completed={["HireLoop scored and analyzed every eligible opportunity from this search."]}
                decision="Which opportunity (if any) to pursue next."
                why="HireLoop never applies on your behalf — selecting a target opportunity is a consequential decision reserved for a human."
              />
              <button
                className="hl-btn-primary self-start"
                disabled={acting}
                onClick={() => applyResume({ action: "SELECT", job_id: detail.job_id })}
              >
                Select Opportunity
              </button>
            </>
          ) : (
            <p className="text-[12px] text-muted">This job is not in the current eligible selection set.</p>
          )}
        </div>
      )}
    </div>
  );
}

function OpportunityCard({ o, onDetail }: { o: OpportunityRow; onDetail: () => void }) {
  return (
    <div className="hl-card p-4 flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-[13.5px] truncate flex items-center gap-1.5">
            <span className="truncate">
              {o.title} — {o.company}
            </span>
            {o.job_id === CERTIFICATION_DEMO_JOB_ID && (
              <span
                className="hl-badge hl-badge-violet shrink-0"
                title="Selected to demonstrate both supported and unsupported resume evidence."
              >
                CERTIFICATION DEMO PICK
              </span>
            )}
          </div>
          <div className="text-[11.5px] text-muted truncate">
            {o.location} · {o.work_mode ?? "Work mode unknown"}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-extrabold tabular-nums">{o.score.toFixed(1)}</div>
          <Badge label={o.recommendation} kind="info" />
        </div>
      </div>
      {o.requirement_completeness === "LOW" && (
        <p className="text-[10.5px] text-amber">Limited job-description evidence. Match confidence is reduced.</p>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase text-green">Why HireLoop Likes It</div>
          <ul className="list-disc list-inside text-[11px] text-muted">
            {o.strengths.slice(0, 3).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase text-amber">Watch Out For</div>
          <ul className="list-disc list-inside text-[11px] text-muted">
            {o.gaps.slice(0, 3).map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="flex gap-2">
        <button className="hl-btn-secondary flex-1" onClick={onDetail}>
          View Intelligence
        </button>
        <Link href={`/opportunities/${o.job_id}`} className="hl-btn-secondary flex-1 flex items-center justify-center text-center">
          Full Detail Page
        </Link>
      </div>
    </div>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<div className="text-muted text-[13px] px-1 py-10">Loading…</div>}>
      <OpportunitiesInner />
    </Suspense>
  );
}
