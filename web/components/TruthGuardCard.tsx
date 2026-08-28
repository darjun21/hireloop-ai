import type { TruthGuardSummary } from "@/lib/types";

function truncateEvidence(evidence: string, max = 2): string {
  const ids = evidence.split(",").map((s) => s.trim()).filter(Boolean);
  if (ids.length <= max) return ids.join(", ");
  return `${ids.slice(0, max).join(", ")} +${ids.length - max} more`;
}

export default function TruthGuardCard({ summary }: { summary: TruthGuardSummary }) {
  return (
    <div className="hl-card p-2.5 flex flex-col gap-1.5">
      <div className="text-[11px] font-bold uppercase tracking-wider text-muted">Truth Guard Summary</div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-lg font-extrabold text-green tabular-nums">{summary.counts.verified}</div>
          <div className="text-[9.5px] text-muted">Verified</div>
        </div>
        <div>
          <div className="text-lg font-extrabold text-red tabular-nums">{summary.counts.blocked}</div>
          <div className="text-[9.5px] text-muted">Blocked</div>
        </div>
        <div>
          <div className="text-lg font-extrabold text-amber tabular-nums">{summary.counts.review}</div>
          <div className="text-[9.5px] text-muted">Needs Review</div>
        </div>
      </div>

      {summary.blocked_example && (
        <div className="rounded-lg border p-2" style={{ borderColor: "rgba(255,86,99,.32)", background: "rgba(255,86,99,.06)" }}>
          <div className="text-[9px] font-bold uppercase tracking-wide text-red mb-0.5">Blocked Claim</div>
          <p className="text-[10.5px] mb-0.5 line-clamp-2">{summary.blocked_example.claim}</p>
          <p className="text-[10px] text-muted line-clamp-1">{summary.blocked_example.reason}</p>
        </div>
      )}
      {summary.verified_example && (
        <div className="rounded-lg border p-2" style={{ borderColor: "rgba(45,215,125,.32)", background: "rgba(45,215,125,.06)" }}>
          <div className="text-[9px] font-bold uppercase tracking-wide text-green mb-0.5">Verified Claim</div>
          <p className="text-[10.5px] mb-0.5 line-clamp-2">{summary.verified_example.claim}</p>
          <p className="text-[10px] text-muted line-clamp-1">Evidence: {truncateEvidence(summary.verified_example.evidence ?? "none")}</p>
        </div>
      )}
      {!summary.blocked_example && !summary.verified_example && summary.counts.verified + summary.counts.blocked + summary.counts.review === 0 && (
        <div className="rounded-lg border p-2.5" style={{ borderColor: "rgba(125,160,215,.2)", background: "rgba(125,160,215,.05)" }}>
          <p className="text-[10.5px] font-bold uppercase tracking-wide text-muted mb-1">Waiting For Verification</p>
          <p className="text-[11px] text-muted leading-snug">
            Select an opportunity and prepare resume changes to begin evidence verification.
          </p>
        </div>
      )}
    </div>
  );
}
