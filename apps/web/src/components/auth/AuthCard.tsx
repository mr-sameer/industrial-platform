import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Shared centered-card layout for every page under the (auth) route
 * group (login, register, forgot-password, reset-password,
 * verify-email) — these live outside the AppShell (see src/app/(auth)/
 * layout.tsx), so they need their own minimal, branded chrome rather
 * than the authenticated sidebar/topbar.
 *
 * The "Back to Home" link lives here, centrally, specifically so every
 * auth page gets it automatically — including any added after this
 * comment was written — rather than each page needing to remember to
 * add its own.
 */
export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4 py-12">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex justify-center">
          <span className="font-display text-lg font-semibold tracking-tight text-ink">
            Forge<span className="text-accent">X</span>
          </span>
        </Link>
        <div className="rounded-lg border border-border bg-canvas p-8 shadow-popover">
          <h1 className="font-display text-xl font-semibold text-ink">{title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-6 text-center text-sm text-ink-muted">{footer}</p>
        <Link
          href="/"
          className="mt-4 flex items-center justify-center gap-1.5 text-sm text-ink-muted hover:text-ink"
        >
          <ArrowLeft size={14} aria-hidden />
          Back to Home
        </Link>
      </div>
    </main>
  );
}
