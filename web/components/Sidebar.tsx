"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "./Logo";
import Icon, { IconName } from "./Icon";
import SidebarLoopMini from "./SidebarLoopMini";
import { useSession } from "@/lib/session-context";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Mission Control", icon: "mission_control" },
  { href: "/career-profile", label: "My Career Profile", icon: "human" },
  { href: "/candidate-setup", label: "Run Discovery", icon: "search" },
  { href: "/opportunities", label: "Opportunities", icon: "opportunities" },
  { href: "/resume-studio", label: "Resume Studio", icon: "resume" },
  { href: "/applications", label: "Applications", icon: "applications" },
  { href: "/strategy", label: "Strategy Intelligence", icon: "strategy" },
  { href: "/system", label: "System & Demo", icon: "system" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { mc, mode } = useSession();
  const isDemo = mode === "CERTIFICATION_DEMO";

  return (
    <aside className="hidden lg:flex w-[272px] shrink-0 flex-col bg-sidebar border-r border-border h-screen sticky top-0">
      <div className="flex items-center gap-3 px-5 pt-6 pb-4">
        <Logo size={34} />
        <div>
          <div className="text-[19px] font-extrabold leading-tight tracking-tight">HireLoop AI</div>
          <div className="text-[11px] text-muted leading-snug">
            Every application makes
            <br />
            the next one smarter.
          </div>
        </div>
      </div>

      <div className="px-5 pb-4">
        <span className={`hl-badge ${isDemo ? "hl-badge-violet" : "hl-badge-success"}`}>
          {isDemo ? "DEMO MODE / SYNTHETIC DATA" : "PERSONAL MODE"}
        </span>
      </div>

      <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-muted px-5 pb-1">Workspace</div>
      <nav className="flex flex-col gap-1 px-3">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg pl-2.5 pr-3 py-2.5 text-[13px] font-medium transition-colors border-l-[3px] ${
                active ? "text-white" : "border-transparent text-muted hover:bg-white/5 hover:text-text"
              }`}
              style={
                active
                  ? {
                      background: "linear-gradient(90deg, rgba(139,92,246,.24), rgba(12,27,48,.9))",
                      borderLeftColor: "var(--violet)",
                    }
                  : undefined
              }
            >
              <Icon name={item.icon} size={16} color={active ? "#F6F8FF" : "#8D9AB2"} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex-1" />

      <div className="pb-5 border-t border-border pt-3">
        <SidebarLoopMini stageStatus={mc?.stage_status} />
      </div>
    </aside>
  );
}
