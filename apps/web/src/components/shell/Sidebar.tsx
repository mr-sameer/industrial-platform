"use client";

import { Building2, LayoutDashboard, Search as SearchIcon, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/cn";

// P0 #5 (Buyer UX Audit): Consult is the core buyer workflow, but nothing
// in the authenticated shell pointed back to it — a buyer who registers
// or logs in lands on Dashboard/Companies/Search with no way back except
// re-typing the URL. Listed first since it's the primary entry point, not
// a peer of the other three.
const NAV_ITEMS = [
  { href: "/consult", label: "Ask ForgeX", icon: Sparkles },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/companies/search", label: "Search", icon: SearchIcon },
];

// Phase 2B-1: entry point into the admin verification review queue
// (GET /companies/documents/pending, Phase 2A) — platform-Role.ADMIN
// only, matching the backend's own RequireAdmin gate exactly (see
// app/api/v1/company_verification.py). Kept separate from NAV_ITEMS
// (appended conditionally in NavLinks below) since it's the one entry
// not visible to every authenticated user.
const ADMIN_NAV_ITEM = { href: "/admin/verification", label: "Verification queue", icon: ShieldCheck };

function NavLinks() {
  const pathname = usePathname();
  // useAuth() (not a prop) so both Sidebar and MobileNav — which renders
  // this same component with zero props — automatically get identical,
  // single-source-of-truth role-gating without either needing its own
  // copy of this check.
  const { user } = useAuth();
  const items = user?.role === "admin" ? [...NAV_ITEMS, ADMIN_NAV_ITEM] : NAV_ITEMS;
  return (
    <nav className="flex flex-col gap-0.5 px-3">
      {items.map((item) => {
        const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-sidebar-active text-ink-inverse"
                : "text-ink-inverse-muted hover:bg-sidebar-hover hover:text-ink-inverse"
            )}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={17} aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Desktop-fixed sidebar. `footer` anchors the profile menu at the bottom — see AppShell. */
export function Sidebar({ header, footer }: { header: ReactNode; footer: ReactNode }) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
      <div className="flex h-14 items-center border-b border-sidebar-border px-4">{header}</div>
      <div className="flex-1 overflow-y-auto py-4">
        <NavLinks />
      </div>
      <div className="border-t border-sidebar-border p-3">{footer}</div>
    </aside>
  );
}

export { NavLinks };
