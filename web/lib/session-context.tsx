"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ensureSession, getStoredSessionId, onSessionRecovered, resetSession, SessionRecoveryFailedError } from "./api";
import { fetchSessionMode } from "./career-profile-api";
import type { SessionMode } from "./career-profile-types";
import type { MissionControlView } from "./types";

interface SessionContextValue {
  sessionId: string | null;
  mc: MissionControlView | null;
  mode: SessionMode;
  loading: boolean;
  error: string | null;
  /** True only when the workflow session_id was lost (e.g. a backend
   * restart) AND automatic recovery itself failed -- the Career Profile
   * is never affected either way. Distinct from `error`, which covers
   * any other API failure. See Priority 1 / api.ts's recoverSession(). */
  sessionExpired: boolean;
  refresh: () => Promise<void>;
  startNewSession: () => Promise<void>;
  startDemo: () => Promise<void>;
  startRun: (body: {
    resume_path?: string;
    target_roles: string[];
    work_modes: string[];
    owner_id?: string;
  }) => Promise<void>;
  applyResume: (body: {
    action: string;
    job_id?: string;
    modification_ids?: string[];
    confirmation_detail?: string;
  }) => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mc, setMc] = useState<MissionControlView | null>(null);
  const [mode, setMode] = useState<SessionMode>("PERSONAL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  // A stale session_id can be recovered transparently mid-request by any
  // api.* call (see api.ts's sessionReq/recoverSession) -- this keeps
  // this provider's own sessionId state in sync with the fresh one
  // instead of continuing to hold the dead id.
  useEffect(() => {
    return onSessionRecovered((freshSid) => {
      setSessionId(freshSid);
      setSessionExpired(false);
    });
  }, []);

  const refresh = useCallback(async () => {
    const sid = await ensureSession();
    setSessionId(sid);
    try {
      const view = await api.missionControl(sid);
      setMc(view);
      setError(null);
      setSessionExpired(false);
    } catch (e) {
      if (e instanceof SessionRecoveryFailedError) {
        setSessionExpired(true);
        setError(null);
      } else {
        setError(e instanceof Error ? e.message : "Failed to reach API bridge");
      }
    } finally {
      setLoading(false);
    }
    // Mode is fetched separately -- it never blocks/errors the main
    // mission-control view if unreachable, since it's purely a UI badge.
    //
    // Re-read the CURRENT session_id from localStorage rather than
    // reusing the `sid` closure variable captured above: api.missionControl
    // may have silently recovered a stale `sid` to a fresh one internally
    // (lib/api.ts's sessionReq), synchronously persisting it to
    // localStorage before returning -- `sid` itself is never updated to
    // match. Using the stale value here would still self-heal (
    // fetchSessionMode now goes through the same sessionReq recovery),
    // but would waste a request on every single recovery. localStorage
    // (via getStoredSessionId) is the single authoritative record of
    // "the current session_id" that every recovery path already writes
    // to, so reading it here avoids introducing a second, parallel cache.
    fetchSessionMode(getStoredSessionId() ?? sid)
      .then(setMode)
      .catch(() => {});
  }, []);

  // Controlled recovery path for when automatic mid-request recovery
  // itself failed (backend still unreachable, etc.) -- never touches
  // owner_id/Career Profile, only the disposable session_id.
  const startNewSession = useCallback(async () => {
    resetSession();
    setSessionExpired(false);
    setLoading(true);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data fetch on mount
    refresh();
  }, [refresh]);

  const startDemo = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const view = await api.demoStart(sessionId);
      setMc(view);
      setError(null);
      setMode("CERTIFICATION_DEMO");
    } catch (e) {
      if (e instanceof SessionRecoveryFailedError) setSessionExpired(true);
      else setError(e instanceof Error ? e.message : "Failed to start demo");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const startRun = useCallback(
    async (body: { resume_path?: string; target_roles: string[]; work_modes: string[]; owner_id?: string }) => {
      if (!sessionId) return;
      setLoading(true);
      try {
        const view = await api.run(sessionId, body);
        setMc(view);
        setError(null);
        setMode("PERSONAL");
      } catch (e) {
        if (e instanceof SessionRecoveryFailedError) setSessionExpired(true);
        else setError(e instanceof Error ? e.message : "Failed to start run");
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  const applyResume = useCallback(
    async (body: { action: string; job_id?: string; modification_ids?: string[]; confirmation_detail?: string }) => {
      if (!sessionId) return;
      setLoading(true);
      try {
        const view = await api.resume(sessionId, body);
        setMc(view);
        setError(null);
      } catch (e) {
        if (e instanceof SessionRecoveryFailedError) setSessionExpired(true);
        else setError(e instanceof Error ? e.message : "Failed to submit decision");
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  return (
    <SessionContext.Provider
      value={{ sessionId, mc, mode, loading, error, sessionExpired, refresh, startNewSession, startDemo, startRun, applyResume }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
