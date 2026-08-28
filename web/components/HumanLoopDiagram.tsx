"use client";

import Icon from "./Icon";
import type { StageStatusMap, StageStatus } from "@/lib/types";

interface StageMeta {
  key: keyof StageStatusMap;
  color: string;
  caption: string;
  humanLabel?: "SELECT" | "APPROVE" | "CONFIRM";
}

const STAGES: StageMeta[] = [
  { key: "DISCOVER", color: "#20C8FF", caption: "AI finds opportunities" },
  { key: "SCORE", color: "#8B5CF6", caption: "AI scores fit", humanLabel: "SELECT" },
  { key: "TAILOR", color: "#F5B83D", caption: "AI tailors your resume" },
  { key: "VERIFY", color: "#2DD77D", caption: "Truth Guard checks every claim", humanLabel: "APPROVE" },
  { key: "APPLY", color: "#2585FF", caption: "Application package prepared" },
  { key: "TRACK", color: "#8B5CF6", caption: "Outcome tracked", humanLabel: "CONFIRM" },
  { key: "LEARN", color: "#20C8FF", caption: "AI learns what worked" },
  { key: "IMPROVE", color: "#F5B83D", caption: "Next loop gets smarter" },
];

const STATUS_LABEL: Record<StageStatus, string> = {
  done: "Complete",
  active: "In progress",
  human: "Human decision",
  waiting: "Waiting",
};

export default function HumanLoopDiagram({ stageStatus }: { stageStatus?: StageStatusMap }) {
  const n = STAGES.length;
  const w = 780;
  const h = 264;
  const cx = w / 2;
  const cy = h / 2;
  const r = 88;

  const positions = STAGES.map((meta, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    return { ...meta, angle, x, y, status: stageStatus?.[meta.key] ?? "waiting" };
  });

  return (
    <div className="relative w-full flex justify-center">
      <div className="relative" style={{ width: "100%", maxWidth: w }}>
        <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
          {/* luminous circular connector */}
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(125,160,215,.22)" strokeWidth="1.5" />
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="url(#hl-loop-grad)" strokeWidth="1.5" strokeDasharray="1 7" strokeLinecap="round" opacity="0.9" />
          <defs>
            <linearGradient id="hl-loop-grad" x1="0" y1="0" x2={w} y2={h} gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="#20C8FF" />
              <stop offset="1" stopColor="#8B5CF6" />
            </linearGradient>
            <radialGradient id="hl-center-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* human-decision dotted connectors */}
          {positions
            .filter((p) => p.humanLabel)
            .map((p) => {
              const lx = cx + (r + 66) * Math.cos(p.angle);
              const ly = cy + (r + 66) * Math.sin(p.angle);
              const active = p.status === "human";
              return (
                <g key={`hd-${p.key}`}>
                  <line
                    x1={p.x}
                    y1={p.y}
                    x2={lx}
                    y2={ly}
                    stroke={active ? "#8B5CF6" : "rgba(139,92,246,.35)"}
                    strokeWidth={active ? 1.6 : 1}
                    strokeDasharray="3 3"
                  />
                  <rect
                    x={lx - 26}
                    y={ly - 9}
                    width="52"
                    height="18"
                    rx="9"
                    fill={active ? "rgba(139,92,246,.22)" : "rgba(139,92,246,.08)"}
                    stroke={active ? "#8B5CF6" : "rgba(139,92,246,.35)"}
                    strokeWidth="1"
                    className={active ? "hl-human-glow" : undefined}
                  />
                  <text x={lx} y={ly + 3.5} textAnchor="middle" fontSize="8.5" fontWeight={800} fill={active ? "#F6F8FF" : "#8B5CF6"}>
                    {p.humanLabel}
                  </text>
                </g>
              );
            })}

          {/* center glow */}
          <circle cx={cx} cy={cy} r={66} fill="url(#hl-center-glow)" />

          {/* stage nodes */}
          {positions.map((p) => {
            const isWaiting = p.status === "waiting";
            const isDone = p.status === "done";
            const isActive = p.status === "active";
            const isHuman = p.status === "human";
            return (
              <g key={p.key} className={isActive ? "hl-node-active" : undefined} style={{ color: p.color }}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={17}
                  fill={isDone || isActive || isHuman ? `${p.color}22` : "#0B1628"}
                  stroke={p.color}
                  strokeWidth={isWaiting ? 1.2 : 2.1}
                  opacity={isWaiting ? 0.4 : 1}
                />
                {isDone && (
                  <path
                    d={`M${p.x - 4.3} ${p.y}l3 3 5.6-5.6`}
                    stroke={p.color}
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    fill="none"
                  />
                )}
                {isHuman && <circle cx={p.x} cy={p.y} r="2.6" fill={p.color} />}
              </g>
            );
          })}

          {/* labels — placed radially outward from each node so they never
              cross the SELECT/APPROVE/CONFIRM callouts, which sit further
              out along the same radial line. */}
          {positions.map((p) => {
            const below = p.y > cy;
            const lx = cx + (r + 30) * Math.cos(p.angle);
            const ly = cy + (r + 30) * Math.sin(p.angle) + (below ? 3 : 0);
            return (
              <g key={`lbl-${p.key}`}>
                <text x={lx} y={ly} textAnchor="middle" fontSize="9.5" fontWeight={800} fill={p.color} letterSpacing="0.03em">
                  {p.key}
                </text>
                <text
                  x={lx}
                  y={ly + (below ? 11 : -10)}
                  textAnchor="middle"
                  fontSize="7.5"
                  fill="#91A0B8"
                >
                  {STATUS_LABEL[p.status]}
                </text>
              </g>
            );
          })}
        </svg>

        {/* center content */}
        <div
          className="absolute flex flex-col items-center text-center gap-1"
          style={{ left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: 148 }}
        >
          <Icon name="human" size={22} color="var(--violet)" />
          <div className="text-[11px] font-extrabold tracking-tight">HUMAN IN THE LOOP</div>
          <div className="text-[9px] text-muted leading-snug">You decide. HireLoop handles the heavy lifting.</div>
        </div>
      </div>

      <div className="hidden xl:grid absolute right-[-8px] top-2 grid-cols-1 gap-y-1.5 text-[9.5px] w-[160px]">
        {positions.map((p) => (
          <div key={`legend-${p.key}`} className="flex items-start gap-1.5" style={{ opacity: p.status === "waiting" ? 0.5 : 1 }}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-1" style={{ background: p.color }} />
            <span className="text-muted leading-snug">{p.caption}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
