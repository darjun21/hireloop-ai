import type { StageStatusMap } from "@/lib/types";

const LOOP_STAGES: (keyof StageStatusMap)[] = [
  "DISCOVER",
  "SCORE",
  "TAILOR",
  "VERIFY",
  "TRACK",
  "LEARN",
  "IMPROVE",
];

const COLOR: Record<string, string> = {
  done: "#2DD77D",
  active: "#20C8FF",
  human: "#8B5CF6",
  waiting: "#3A4560",
};

export default function SidebarLoopMini({ stageStatus }: { stageStatus?: StageStatusMap }) {
  const n = LOOP_STAGES.length;
  const size = 150;
  const cx = 75;
  const cy = 75;
  const r = 54;

  const nodes = LOOP_STAGES.map((stage, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    const status = stageStatus?.[stage] ?? "waiting";
    const color = COLOR[status];
    const lx = cx + (r + 13) * Math.cos(angle);
    const ly = cy + (r + 13) * Math.sin(angle);
    let anchor: "start" | "middle" | "end" = "middle";
    if (lx < cx - 8) anchor = "end";
    else if (lx > cx + 8) anchor = "start";
    return (
      <g key={stage}>
        <circle cx={x} cy={y} r={4.2} fill={color} />
        <text
          x={lx}
          y={ly}
          textAnchor={anchor}
          fontSize="6.2"
          fontWeight={700}
          fill={color}
          style={{ fontFamily: "var(--font-inter), Inter, sans-serif" }}
        >
          {stage.slice(0, 4)}
        </text>
      </g>
    );
  });

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="w-full text-[10px] font-bold uppercase tracking-wider text-muted px-3">The HireLoop</div>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(120,160,220,.16)" strokeWidth="1.4" strokeDasharray="2 3" />
        {nodes}
        <circle cx={cx} cy={cy} r={19} fill="rgba(139,92,246,.10)" stroke="rgba(139,92,246,.4)" strokeWidth="1" />
        <circle cx={cx} cy={cy - 4} r={3.4} fill="#F5F7FF" />
        <path d={`M${cx - 6} ${cy + 9}c0-4.6 2.9-7.6 6-7.6s6 3 6 7.6`} stroke="#F5F7FF" strokeWidth="2.6" strokeLinecap="round" fill="none" />
      </svg>
      <div className="text-center text-[10px] italic text-muted px-3 leading-snug">
        Human decides. AI works around you. Every outcome improves the next loop.
      </div>
    </div>
  );
}
