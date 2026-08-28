import Icon, { IconName } from "./Icon";
import type { Kpi } from "@/lib/types";

export default function KpiRow({ items }: { items: Kpi[] }) {
  return (
    <div className="grid grid-cols-5 gap-3">
      {items.map((item) => (
        <div key={item.label} className="hl-card flex items-center gap-3 px-3.5 py-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: "rgba(139,92,246,.14)" }}>
            <Icon name={item.icon as IconName} size={15} color="var(--violet)" />
          </div>
          <div className="min-w-0">
            <div className="text-[22px] font-extrabold leading-none tabular-nums">{item.value}</div>
            <div className="text-[10px] text-muted mt-1 truncate">{item.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
