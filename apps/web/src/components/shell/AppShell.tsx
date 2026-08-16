"use client";

import type { ReactNode } from "react";

import { Footer } from "@/components/shell/Footer";
import { ProfileMenu } from "@/components/shell/ProfileMenu";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { useRequireAuth } from "@/hooks/useRequireAuth";

function Brand() {
  return (
    <span className="font-display text-sm font-semibold tracking-tight text-ink-inverse">
      Forge<span className="text-accent">X</span>
    </span>
  );
}

/**
 * The authenticated app shell — sidebar + top bar + footer, wrapping
 * every page under the (app) route group (see
 * src/app/(app)/layout.tsx). Owns the auth guard itself so individual
 * pages don't each need their own useRequireAuth call for the
 * shell-level "must be signed in" check.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const auth = useRequireAuth("/dashboard");

  if (auth.status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
      </div>
    );
  }
  if (auth.status === "unauthenticated") return null;

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar header={<Brand />} footer={<ProfileMenu />} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">{children}</main>
        <Footer />
      </div>
    </div>
  );
}
