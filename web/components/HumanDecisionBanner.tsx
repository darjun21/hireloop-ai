import Icon from "./Icon";

export default function HumanDecisionBanner({
  completed,
  decision,
  why,
}: {
  completed: string[];
  decision: string;
  why: string;
}) {
  return (
    <div
      className="rounded-xl border p-3 flex flex-col gap-1.5"
      style={{ borderColor: "rgba(139,92,246,.4)", background: "rgba(139,92,246,.08)" }}
    >
      <div className="flex items-center gap-2">
        <Icon name="human" size={17} color="var(--violet)" />
        <span className="font-bold text-[13.5px]">Human Decision Required</span>
      </div>
      <p className="text-[11.5px] text-muted">HireLoop completed the autonomous work. The next decision is yours.</p>
      {completed.map((line, i) => (
        <div key={i} className="flex items-start gap-1.5 text-[12px]">
          <Icon name="check" size={12} color="var(--green)" className="mt-0.5 shrink-0" />
          <span>{line}</span>
        </div>
      ))}
      <p className="text-[12px]">
        <span className="font-semibold">Waiting on: </span>
        {decision}
      </p>
      <p className="text-[12px] text-muted">
        <span className="font-semibold text-text">Why a human: </span>
        {why}
      </p>
    </div>
  );
}
