"use client";

import Link from "next/link";
import Badge from "./Badge";
import ScoreRing from "./ScoreRing";
import { useSession } from "@/lib/session-context";
import type { TopOpportunity } from "@/lib/types";

export default function TopOpportunityCard({ opp }: { opp: TopOpportunity }) {
  const { applyResume, loading } = useSession();

  return (
    <div className="hl-card p-3.5 flex flex-col gap-2.5">
      <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Top Opportunity</div>
      <div className="flex items-start gap-4">
        <ScoreRing value={opp.score} size={80} />
        <div className="flex-1 min-w-0">
          <div className="text-lg font-bold truncate">{opp.title}</div>
          <div className="text-[13px] text-muted truncate">
            {opp.company} · {opp.location}
            {opp.work_mode ? ` · ${opp.work_mode}` : ""}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Badge label={opp.recommendation} kind="info" />
            <Badge label={opp.confidence} />
          </div>
        </div>
      </div>

      {(opp.strengths.length > 0 || opp.gaps.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wide text-green mb-1.5">Top Matches</div>
            <ul className="space-y-1 text-[12.5px] text-muted list-disc list-inside">
              {opp.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wide text-amber mb-1.5">Top Gaps</div>
            <ul className="space-y-1 text-[12.5px] text-muted list-disc list-inside">
              {opp.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="flex gap-3 mt-1">
        <Link
          href={`/opportunities?job=${opp.job_id}`}
          className="hl-btn-secondary flex-1 flex items-center justify-center text-center"
        >
          View Intelligence
        </Link>
        <button
          className="hl-btn-primary flex-1"
          disabled={!opp.selectable || loading}
          onClick={() => applyResume({ action: "SELECT", job_id: opp.job_id })}
          title={opp.selectable ? "Select this opportunity" : "Not currently eligible for selection"}
        >
          Select Opportunity
        </button>
      </div>
    </div>
  );
}
