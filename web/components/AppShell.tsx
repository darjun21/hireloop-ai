"use client";

import { SessionProvider } from "@/lib/session-context";
import Sidebar from "./Sidebar";
import Header from "./Header";
import SessionRecoveryBanner from "./SessionRecoveryBanner";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <SessionRecoveryBanner />
          <main className="flex-1 min-w-0 px-6 py-4">{children}</main>
        </div>
      </div>
    </SessionProvider>
  );
}
