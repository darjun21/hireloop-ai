import Badge from "./Badge";
import Icon, { IconName } from "./Icon";
import type { AgentActivityRow } from "@/lib/types";

const AGENT_ICON: Record<string, IconName> = {
  "Profile Agent": "resume",
  "Job Scout": "search",
  "Match Analyst": "chart",
  "Resume Tailor": "bolt",
  "Truth Guard": "shield_x",
  "Learning Agent": "star",
};

const AGENT_COLOR: Record<string, string> = {
  "Profile Agent": "#20C8FF",
  "Job Scout": "#2585FF",
  "Match Analyst": "#8B5CF6",
  "Resume Tailor": "#F5B83D",
  "Truth Guard": "#2DD77D",
  "Learning Agent": "#20C8FF",
};

export default function AgentActivityRail({ rows, dense = false }: { rows: AgentActivityRow[]; dense?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[11px] font-bold uppercase tracking-wider text-muted px-1">AI Team Activity</div>
      {rows.map((row) => {
        const color = AGENT_COLOR[row.name] ?? "#8B5CF6";
        return (
          <div key={row.name} className={`hl-card px-3 flex items-center gap-2.5 ${dense ? "py-1.5" : "py-2"}`}>
            <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0" style={{ background: `${color}22` }}>
              <Icon name={AGENT_ICON[row.name] ?? "bolt"} size={12} color={color} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11.5px] font-semibold truncate">{row.name}</div>
              {!dense && <p className="text-[10.5px] text-muted truncate leading-snug">{row.note}</p>}
            </div>
            <Badge label={row.status} />
          </div>
        );
      })}
    </div>
  );
}
