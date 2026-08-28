"use client";

import { useEffect, useState } from "react";
import Badge from "@/components/Badge";
import InsightCard from "@/components/InsightCard";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { GroupAnalytics, StrategyView } from "@/lib/types";

function BarRows({ rows }: { rows: [string, number, string][] }) {
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map(([label, pct, right]) => (
        <div key={label}>
          <div className="flex justify-between text-[11.5px] mb-1">
            <span className="font-medium">{label}</span>
            <span className="text-muted">{right}</span>
          </div>
          <div className="h-1.5 rounded-full bg-card-alt overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: "linear-gradient(90deg,#20C8FF,#8B5CF6)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function StrategyPage() {
  const { sessionId, mc } = useSession();
  const [view, setView] = useState<StrategyView | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    api.strategy(sessionId).then(setView).catch(() => setView(null));
  }, [sessionId, mc]);

  if (!view) return <div className="text-muted text-[13px] px-1 py-10">Loading Strategy Intelligence…</div>;

  const resolved = Object.entries(view.analytics.by_role_family).filter(([, g]) => g.sample_size > 0);

  return (
    <div className="flex flex-col gap-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Strategy Intelligence</h1>
        <p className="text-[12.5px] text-muted mt-0.5">What&apos;s actually working?</p>
        {view.demo_mode && (
          <div className="mt-1.5">
            <Badge label="DEMO MODE" kind="violet" /> <span className="text-[11px] text-muted">figures below include synthetic seeded history.</span>
          </div>
        )}
      </div>

      {resolved.length > 0 ? (
        <>
          <div className="hl-card p-5">
            <div className="text-[12px] font-semibold mb-3">Interview rate by role family</div>
            <BarRows
              rows={resolved
                .sort((a, b) => b[1].interview_rate - a[1].interview_rate)
                .map(([name, g]) => [name, g.interview_rate * 100, `${(g.interview_rate * 100).toFixed(1)}% (${g.interviews}/${g.sample_size})`])}
            />
          </div>
          <div className="hl-card p-5">
            <div className="text-[12px] font-semibold mb-3">Response rate by role family</div>
            <BarRows
              rows={resolved
                .sort((a, b) => b[1].response_rate - a[1].response_rate)
                .map(([name, g]) => [name, g.response_rate * 100, `${(g.response_rate * 100).toFixed(1)}% (${g.positive_responses}/${g.sample_size})`])}
            />
          </div>
        </>
      ) : (
        <p className="text-[12.5px] text-muted">Not enough resolved data yet for a role-family comparison.</p>
      )}

      <button className="hl-btn-secondary self-start" onClick={() => setShowRaw((s) => !s)}>
        {showRaw ? "Hide" : "View"} Raw Data
      </button>
      {showRaw && (
        <div className="flex flex-col gap-4">
          <GroupTable title="By role family" groups={view.analytics.by_role_family} />
          <GroupTable title="By resume version" groups={view.analytics.by_resume_version} />
          <GroupTable title="By work mode" groups={view.analytics.by_work_mode} />
        </div>
      )}

      <div>
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-3">HireLoop Strategy Insights</div>
        {view.insights.length === 0 ? (
          <p className="text-[12.5px] text-muted">No strategy insights recorded yet.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {view.insights.map((insight, i) => (
              <InsightCard key={i} insight={insight} linkToStrategy={false} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function GroupTable({ title, groups }: { title: string; groups: Record<string, GroupAnalytics> }) {
  const rows = Object.entries(groups).filter(([, g]) => g.sample_size > 0);
  return (
    <div className="hl-card p-4 overflow-x-auto">
      <div className="text-[12px] font-semibold mb-2">{title}</div>
      {rows.length === 0 ? (
        <p className="text-[11.5px] text-muted">No data yet.</p>
      ) : (
        <table className="w-full text-[11.5px]">
          <thead className="text-muted text-left">
            <tr>
              <th className="pr-4 py-1">Group</th>
              <th className="pr-4">Apps</th>
              <th className="pr-4">Response Rate</th>
              <th className="pr-4">Interview Rate</th>
              <th className="pr-4">Offer Rate</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, g]) => (
              <tr key={name} className="border-t border-border">
                <td className="pr-4 py-1">{name}</td>
                <td className="pr-4">{g.sample_size}</td>
                <td className="pr-4">{(g.response_rate * 100).toFixed(1)}%</td>
                <td className="pr-4">{(g.interview_rate * 100).toFixed(1)}%</td>
                <td className="pr-4">{(g.offer_rate * 100).toFixed(1)}%</td>
                <td>{g.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
