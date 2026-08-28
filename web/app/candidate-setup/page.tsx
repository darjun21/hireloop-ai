"use client";

import { useState } from "react";
import { useSession } from "@/lib/session-context";

const ROLE_OPTIONS = ["AI Engineer", "Data Scientist", "ML Engineer", "Backend Engineer"];
const MODE_OPTIONS = ["Remote", "Hybrid", "Onsite"];

export default function CandidateSetupPage() {
  const { mc, startRun, loading } = useSession();
  const [roles, setRoles] = useState<string[]>(["AI Engineer"]);
  const [modes, setModes] = useState<string[]>(["Remote"]);

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  return (
    <div className="flex flex-col gap-5 max-w-[820px]">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Candidate Setup</h1>
        <p className="text-[12.5px] text-muted mt-0.5">
          Point HireLoop at the demo resume and choose which roles and work modes to search for. This calls the
          real backend discovery run — no results are fabricated.
        </p>
      </div>

      <div className="hl-card p-5 flex flex-col gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Target Roles</div>
          <div className="flex flex-wrap gap-2">
            {ROLE_OPTIONS.map((r) => (
              <button
                key={r}
                type="button"
                className={`hl-badge ${roles.includes(r) ? "hl-badge-violet" : "hl-badge-info"}`}
                onClick={() => toggle(roles, setRoles, r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-muted mb-2">Work Mode</div>
          <div className="flex flex-wrap gap-2">
            {MODE_OPTIONS.map((m) => (
              <button
                key={m}
                type="button"
                className={`hl-badge ${modes.includes(m) ? "hl-badge-violet" : "hl-badge-info"}`}
                onClick={() => toggle(modes, setModes, m)}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        <div className="text-[11.5px] text-muted">
          Resume source: the certified demo candidate resume (synthetic, bundled with HireLoop&apos;s eval fixtures).
        </div>

        <button
          className="hl-btn-primary self-start"
          disabled={loading || roles.length === 0 || modes.length === 0}
          onClick={() => startRun({ target_roles: roles, work_modes: modes })}
        >
          {loading ? "Running…" : "Run Discovery"}
        </button>

        {mc?.has_run && (
          <p className="text-[11.5px] text-green">
            A discovery run has completed for this session — see Mission Control for results.
          </p>
        )}
      </div>
    </div>
  );
}
