import Icon from "./Icon";
import type { ActivityEvent } from "@/lib/types";

export default function RecentActivity({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="hl-card p-3">
      <div className="text-[11px] font-bold uppercase tracking-wider text-muted mb-2">Recent Activity</div>
      {events.length === 0 ? (
        <p className="text-[12px] text-muted">No activity recorded yet for this run.</p>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-1">
          {events.map((e, i) => (
            <div key={i} className="flex items-start gap-2 shrink-0 max-w-[260px]">
              <Icon name="clock" size={13} color="var(--muted)" className="mt-0.5 shrink-0" />
              <div>
                {e.timestamp && <div className="text-[10px] text-muted mb-0.5">{e.timestamp}</div>}
                <div className="text-[12px] leading-snug">{e.message}</div>
              </div>
              {i < events.length - 1 && <div className="w-px bg-border self-stretch ml-2" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
