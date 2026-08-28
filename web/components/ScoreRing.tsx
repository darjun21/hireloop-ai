export default function ScoreRing({ value, size = 108 }: { value: number; size?: number }) {
  const r = size / 2 - 8;
  const circumference = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const offset = circumference * (1 - pct);
  const c = size / 2;
  const gradId = `hl-score-ring-${size}`;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(120,160,220,.16)" strokeWidth="8" />
      <circle
        cx={c}
        cy={c}
        r={r}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${c} ${c})`}
      />
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2={size} y2={size} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#20C8FF" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      <text x={c} y={c + 7} textAnchor="middle" fontSize="22" fontWeight={800} fill="#F5F7FF">
        {value.toFixed(0)}
      </text>
    </svg>
  );
}
