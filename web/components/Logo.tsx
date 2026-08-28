// HireLoop AI mark: two overlapping loop rings (cyan -> violet gradient)
// with a small geometric human silhouette set inside the right ring's
// opening — "human in the loop." Pure SVG, no external assets.
//
// Two variants:
//  - Full mark (compact=false): both rings traced in full, for the sidebar.
//  - Compact mark (compact=true): simplified to a single ring + human, so
//    it stays legible at 24-32px in the header / favicon.
//
// Motion: a bright highlight arc travels once around the outer ring on a
// ~6s loop ("light travels around the loop"). The human silhouette never
// animates. Respects prefers-reduced-motion via the .hl-logo-anim class,
// which is disabled entirely under `reduce` (see globals.css).

export default function Logo({
  size = 30,
  animated = true,
  compact = false,
}: {
  size?: number;
  animated?: boolean;
  compact?: boolean;
}) {
  const gradId = compact ? "hl-logo-grad-compact" : "hl-logo-grad-full";

  if (compact) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="HireLoop AI"
      >
        <defs>
          <linearGradient id={gradId} x1="4" y1="8" x2="60" y2="56" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#20C8FF" />
            <stop offset="1" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>
        {/* single ring, thicker stroke for legibility at small sizes */}
        <circle cx="32" cy="32" r="24" stroke={`url(#${gradId})`} strokeWidth="6.5" fill="none" />
        {animated && (
          <circle
            cx="32"
            cy="32"
            r="24"
            stroke="#F6F8FF"
            strokeWidth="6.5"
            strokeLinecap="round"
            fill="none"
            strokeDasharray="18 132"
            className="hl-logo-anim-compact"
            style={{ opacity: 0.9 }}
          />
        )}
        {/* static human silhouette, centered */}
        <circle cx="32" cy="24.5" r="6.2" fill="#F6F8FF" />
        <path d="M20.5 46c0-8 5-13.2 11.5-13.2S43.5 38 43.5 46" stroke="#F6F8FF" strokeWidth="5.4" strokeLinecap="round" fill="none" />
      </svg>
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="HireLoop AI"
    >
      <defs>
        <linearGradient id={gradId} x1="4" y1="8" x2="60" y2="56" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#20C8FF" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      {/* left loop */}
      <circle cx="24" cy="32" r="19" stroke={`url(#${gradId})`} strokeWidth="4.4" fill="none" />
      {/* right loop, opening at bottom-right to host the human silhouette */}
      <path
        d="M 59 32 A 19 19 0 1 1 40.2 15.6"
        stroke={`url(#${gradId})`}
        strokeWidth="4.4"
        strokeLinecap="round"
        fill="none"
      />
      {animated && (
        <circle
          cx="24"
          cy="32"
          r="19"
          stroke="#F6F8FF"
          strokeWidth="4.4"
          strokeLinecap="round"
          fill="none"
          strokeDasharray="14 105"
          className="hl-logo-anim"
          style={{ opacity: 0.85 }}
        />
      )}
      {/* human silhouette nested inside the right ring's opening — static, never animated */}
      <circle cx="42.5" cy="27" r="4.6" fill="#F6F8FF" />
      <path
        d="M33.5 45c0-6.4 4.2-10.6 9-10.6s9 4.2 9 10.6"
        stroke="#F6F8FF"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
