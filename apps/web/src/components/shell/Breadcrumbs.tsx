"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

const LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  companies: "Companies",
  new: "New",
  search: "Search",
  settings: "Settings",
  verification: "Verification",
  "business-info": "Business Information",
  documents: "Documents",
  branding: "Branding",
  "social-links": "Social Links",
  account: "Account",
  sessions: "Sessions",
  company: "Company",
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Derived purely from the URL path — no extra data fetching for a
 * company's real name here (kept intentionally lightweight for a
 * shared shell component; a page-specific header can show the real
 * name where it already has that data loaded, e.g. the Company
 * Dashboard page's own <h1>).
 */
export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-ink-muted">
      <Link href="/dashboard" className="hover:text-ink transition-colors">
        Home
      </Link>
      {segments.map((segment, index) => {
        const href = `/${segments.slice(0, index + 1).join("/")}`;
        const isLast = index === segments.length - 1;
        const label = UUID_PATTERN.test(segment) ? "Details" : (LABELS[segment] ?? segment);
        return (
          <Fragment key={href}>
            <ChevronRight size={14} className="text-ink-faint" aria-hidden />
            {isLast ? (
              <span className="font-medium text-ink" aria-current="page">
                {label}
              </span>
            ) : (
              <Link href={href} className="hover:text-ink transition-colors">
                {label}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
