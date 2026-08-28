import Link from "next/link";
import Badge from "./Badge";
import type { LatestInsight } from "@/lib/types";

export default function InsightCard({ insight, linkToStrategy = true }: { insight: LatestInsight | null; linkToStrategy?: boolean }) {
  return (
    <div className="hl-card p-3.5 flex flex-col gap-2">
      <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Latest HireLoop Insight</div>
      {!insight ? (
        <p className="text-[12.5px] text-muted">No strategy insights recorded yet — record an outcome to generate one.</p>
      ) : (
        <>
          <Badge label={insight.category} kind="violet" />
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-muted mb-1">Observed Data</div>
              <p className="text-[12.5px]">{insight.evidence}</p>
            </div>
            <div>
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-muted mb-1">AI Interpretation</div>
              <p className="text-[12.5px]">{insight.observation}</p>
            </div>
          </div>
          <p className="text-[12.5px]">
            <span className="font-semibold">Recommendation: </span>
            {insight.recommendation}
          </p>
          <div className="flex items-center gap-4 text-[11px] text-muted">
            <span>Sample size: {insight.sample_size}</span>
            <span>Confidence: {insight.confidence}</span>
            <span>Actionability: {insight.actionability ?? "NO_CLEAR_SIGNAL"}</span>
          </div>
          {linkToStrategy && (
            <Link href="/strategy" className="hl-btn-secondary self-start mt-1">
              View Full Strategy
            </Link>
          )}
        </>
      )}
    </div>
  );
}
