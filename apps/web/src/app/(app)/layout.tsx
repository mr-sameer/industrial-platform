import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";

/**
 * Every route under this group (dashboard, companies, account) gets the
 * real application shell (sidebar, top bar, breadcrumbs, command
 * search) — see docs/architecture/design-system.md. `/company/[slug]`
 * (the public profile) is deliberately outside this group — it's a
 * public page and shouldn't render an authenticated sidebar.
 */
export default function AppRouteGroupLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
