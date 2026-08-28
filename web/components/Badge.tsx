const KIND_MAP: Record<string, string> = {
  COMPLETE: "success",
  VERIFIED: "success",
  AVAILABLE: "success",
  CONFIGURED: "success",
  READY: "success",
  WORKING: "info",
  MOCK: "info",
  HIGH: "success",
  MEDIUM: "warning",
  LOW: "danger",
  PARTIALLY_SUPPORTED: "warning",
  "NEEDS REVIEW": "warning",
  NEEDS_HUMAN_CONFIRMATION: "violet",
  DEGRADED: "warning",
  UNSUPPORTED: "danger",
  UNAVAILABLE: "danger",
  WAITING: "neutral",
};

export default function Badge({ label, kind }: { label: string; kind?: string }) {
  const resolved = kind || KIND_MAP[label] || "neutral";
  return <span className={`hl-badge hl-badge-${resolved}`}>{label}</span>;
}
