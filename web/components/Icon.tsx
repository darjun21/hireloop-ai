// Minimal line-icon set, pure inline SVG (no icon library dependency).

type IconName =
  | "mission_control"
  | "opportunities"
  | "resume"
  | "applications"
  | "strategy"
  | "system"
  | "search"
  | "star"
  | "send"
  | "mic"
  | "chart"
  | "human"
  | "check"
  | "shield_x"
  | "bolt"
  | "clock";

const PATHS: Record<IconName, React.ReactNode> = {
  mission_control: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
    </>
  ),
  opportunities: (
    <>
      <rect x="4" y="9" width="16" height="10" rx="1.6" />
      <path d="M9 9V7a3 3 0 0 1 6 0v2" />
    </>
  ),
  resume: (
    <>
      <rect x="5" y="3.5" width="14" height="17" rx="1.4" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  applications: (
    <>
      <path d="M4 7h16M4 12h16M4 17h10" />
    </>
  ),
  strategy: (
    <>
      <path d="M4 20V10M11 20V4M18 20v-7" />
    </>
  ),
  system: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.4M12 18.6V21M21 12h-2.4M5.4 12H3M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7M18.4 18.4l-1.7-1.7M7.3 7.3 5.6 5.6" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m20 20-4.4-4.4" />
    </>
  ),
  star: <path d="M12 3.5 14.5 9l6 .8-4.4 4 1.2 5.9L12 16.8 6.7 19.7l1.2-5.9-4.4-4L9.5 9Z" />,
  send: <path d="m4 12 16-8-6 16-3-6-6-2Z" />,
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v3.5M9 20.5h6" />
    </>
  ),
  chart: <path d="M5 19V9M11 19V5M17 19v-7" />,
  human: (
    <>
      <circle cx="12" cy="8.5" r="3.2" />
      <path d="M6 20c0-4 2.7-6.6 6-6.6s6 2.6 6 6.6" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7" />,
  shield_x: (
    <>
      <path d="M12 3.5 19 6.5v5.6C19 17.4 15.9 20 12 21.2 8.1 20 5 17.4 5 12.1V6.5Z" />
      <path d="m9.5 9.5 5 5m0-5-5 5" />
    </>
  ),
  bolt: <path d="M13 2 4 14h6l-1 8 9-12h-6z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
};

export default function Icon({
  name,
  size = 16,
  color = "currentColor",
  strokeWidth = 1.8,
  className,
}: {
  name: IconName;
  size?: number;
  color?: string;
  strokeWidth?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}

export type { IconName };
