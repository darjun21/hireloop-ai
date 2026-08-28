export default function ScoreBar({
  label,
  value,
  weight,
  contribution,
}: {
  label: string;
  value: number;
  weight: number;
  contribution: number;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-[11.5px]">
        <span className="font-medium">{label}</span>
        <span className="text-muted">
          {value.toFixed(1)}/100 · weight {(weight * 100).toFixed(0)}% · contributes {contribution.toFixed(1)} pts
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-card-alt overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: "linear-gradient(90deg,#20C8FF,#8B5CF6)" }}
        />
      </div>
    </div>
  );
}
