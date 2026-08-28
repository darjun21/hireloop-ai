"use client";

import Logo from "./Logo";
import Icon from "./Icon";

// Real modal for a pending human-in-the-loop interrupt. Dims the page
// behind it, but never hides Truth Guard / agent status / demo disclosure
// (those live in the page underneath and stay mounted). Every action
// button passed in `actions` must call a real backend endpoint via
// session-context's applyResume — this component holds no workflow state
// of its own.

export default function HumanDecisionModal({
  title = "Human Decision Required",
  subtitle = "HireLoop completed the autonomous work. The next decision is yours.",
  completed,
  decision,
  why,
  children,
  onDismiss,
  maxWidth = 560,
}: {
  title?: string;
  subtitle?: string;
  completed: string[];
  decision: string;
  why: string;
  children?: React.ReactNode;
  onDismiss?: () => void;
  maxWidth?: number;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: "rgba(2,6,14,.72)", backdropFilter: "blur(2px)" }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="hl-card w-full p-6 flex flex-col gap-3 hl-decision-halo overflow-y-auto"
        style={{ borderColor: "rgba(139,92,246,.5)", maxWidth, maxHeight: "88vh" }}
      >
        <div className="flex items-center gap-3">
          <Logo size={30} />
          <div>
            <div className="text-[15px] font-extrabold tracking-tight">{title}</div>
            <p className="text-[11.5px] text-muted">{subtitle}</p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5 mt-1">
          {completed.map((line, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[12px]">
              <Icon name="check" size={12} color="var(--green)" className="mt-0.5 shrink-0" />
              <span>{line}</span>
            </div>
          ))}
        </div>

        <p className="text-[12.5px]">
          <span className="font-semibold">Waiting on: </span>
          {decision}
        </p>
        <p className="text-[12px] text-muted">
          <span className="font-semibold text-text">Why a human: </span>
          {why}
        </p>

        {children}

        {onDismiss && (
          <button className="hl-btn-secondary self-end mt-1" onClick={onDismiss}>
            Review on page
          </button>
        )}
      </div>
    </div>
  );
}
