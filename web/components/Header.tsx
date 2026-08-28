"use client";

import Logo from "./Logo";
import { useSession } from "@/lib/session-context";

export default function Header() {
  const { mc } = useSession();
  const demoMode = mc?.demo_mode ?? true;

  return (
    <header className="h-[70px] shrink-0 flex items-center gap-3 px-6 border-b border-border bg-body/80 backdrop-blur sticky top-0 z-10">
      <div className="flex items-center gap-2.5">
        <Logo size={24} compact />
        <div>
          <div className="text-[14px] font-bold leading-none">HireLoop AI</div>
          <div className="text-[9.5px] text-muted mt-0.5 hidden sm:block">Every application makes the next one smarter.</div>
        </div>
      </div>
      <div className="flex-1" />
      <span className={`hl-badge ${demoMode ? "hl-badge-violet" : "hl-badge-info"}`}>
        {demoMode ? "DEMO MODE — SYNTHETIC DATA" : "LIVE MODE"}
      </span>
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-green opacity-60 animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green" />
        </span>
        System Status: Operational
      </div>
    </header>
  );
}
