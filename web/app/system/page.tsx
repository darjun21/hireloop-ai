"use client";

import { useEffect, useState } from "react";
import Badge from "@/components/Badge";
import { useSession } from "@/lib/session-context";
import { api } from "@/lib/api";
import type { SystemView } from "@/lib/types";

function StatusRow({ label, status, note }: { label: string; status: string; note?: string }) {
  const dotColor: Record<string, string> = {
    AVAILABLE: "var(--green)",
    CONFIGURED: "var(--green)",
    MOCK: "var(--cyan)",
    DEGRADED: "var(--amber)",
    UNAVAILABLE: "var(--red)",
  };
  return (
    <div className="flex items-center gap-3 py-2 border-b border-border last:border-0">
      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dotColor[status] ?? "var(--muted)" }} />
      <span className="text-[12.5px] font-medium w-40 shrink-0">{label}</span>
      <Badge label={status} />
      <span className="text-[11px] text-muted">{note}</span>
    </div>
  );
}

export default function SystemPage() {
  const { sessionId, mc } = useSession();
  const [view, setView] = useState<SystemView | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    api.system(sessionId).then(setView).catch(() => setView(null));
  }, [sessionId, mc]);

  if (!view) return <div className="text-muted text-[13px] px-1 py-10">Loading System &amp; Demo…</div>;

  return (
    <div className="flex flex-col gap-6 max-w-[900px]">
      <h1 className="text-2xl font-extrabold tracking-tight">System &amp; Demo</h1>
      <Badge label={view.demo_mode ? "DEMO MODE" : "LIVE MODE"} kind={view.demo_mode ? "violet" : "info"} />

      <div className="hl-card p-5">
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-2">Provider Status</div>
        <StatusRow label="LLM Provider" status={view.llm_provider.status} note={view.llm_provider.name} />
        <StatusRow label="Fallback LLM" status={view.fallback_llm.status} note={view.fallback_llm.name} />
        <StatusRow label="Evidence Retrieval" status={view.evidence_retrieval} note={view.demo_mode ? "Pinecone not configured -> deterministic local fallback active" : ""} />
        <StatusRow label="You.com Live Search" status={view.you_search} note="opt-in, button-gated, never part of the DEMO_MODE certification path" />
      </div>

      <div className="hl-card p-5">
        <div className="text-[13px] font-bold uppercase tracking-wider text-muted mb-2">The HireLoop Loop</div>
        <pre className="text-[11px] text-muted whitespace-pre-wrap">
          {"DISCOVER -> SCORE -> TAILOR -> VERIFY -> APPLY -> TRACK -> LEARN -> IMPROVE\n   ^--------------------------------------------------------------------|"}
        </pre>
      </div>

      <p className="text-[11px] text-muted">
        This Next.js frontend is a separate presentation layer over the same certified backend. The certified
        Streamlit app remains available and unchanged as the certification fallback.
      </p>
    </div>
  );
}
