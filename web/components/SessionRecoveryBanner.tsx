"use client";

import { useSession } from "@/lib/session-context";

// Priority 1 controlled fallback: shown ONLY when a stale session_id
// (e.g. after a backend restart) was detected AND the automatic recovery
// in lib/api.ts's recoverSession() itself also failed (backend still
// unreachable). Never shown for a genuine 404 on some other resource
// (e.g. an unknown job_id), and never implies any Career Profile data
// was touched -- see SessionContextValue.sessionExpired's docstring.
export default function SessionRecoveryBanner() {
  const { sessionExpired, startNewSession } = useSession();
  if (!sessionExpired) return null;

  return (
    <div className="mx-6 mt-3 hl-card border-amber/50 p-3 flex items-center justify-between gap-3">
      <div className="text-[12.5px]">
        <span className="font-semibold text-amber">Your search session expired.</span>{" "}
        <span className="text-muted">Your Career Profile is safe — nothing there was affected.</span>
      </div>
      <button className="hl-btn-secondary shrink-0" onClick={() => startNewSession()}>
        Start New Session
      </button>
    </div>
  );
}
