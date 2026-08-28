"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ensureSession } from "./api";
import type { MissionControlView } from "./types";

interface SessionContextValue {
  sessionId: string | null;
  mc: MissionControlView | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  startDemo: () => Promise<void>;
  startRun: (body: { resume_path?: string; target_roles: string[]; work_modes: string[] }) => Promise<void>;
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const sid = await ensureSession();
    setSessionId(sid);
    try {
      const view = await api.missionControl(sid);
      setMc(view);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach API bridge");
    } finally {
      setLoading(false);
    }
  }, []);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start demo");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const startRun = useCallback(
    async (body: { resume_path?: string; target_roles: string[]; work_modes: string[] }) => {
      if (!sessionId) return;
      setLoading(true);
      try {
        const view = await api.run(sessionId, body);
        setMc(view);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to start run");
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
        setError(e instanceof Error ? e.message : "Failed to submit decision");
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  return (
    <SessionContext.Provider value={{ sessionId, mc, loading, error, refresh, startDemo, startRun, applyResume }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
