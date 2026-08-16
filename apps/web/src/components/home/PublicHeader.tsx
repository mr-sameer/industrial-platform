"use client";

import Link from "next/link";

/**
 * Public homepage header — deliberately minimal. Per explicit product
 * direction: no nav items without a real destination, no anchor links,
 * no placeholder pages. AI Search is the product's primary navigation
 * — companies, manufacturers, suppliers, products, categories, and
 * industries are all discovered through it, not a navbar. Additional
 * nav items return only when those areas become real, complete pages
 * with their own user journeys.
 *
 * No mobile drawer/menu component here (unlike the previous version) —
 * three links plus the logo need no collapsing on any screen size, so
 * a hamburger menu would be complexity with nothing to hide.
 */
export function PublicHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-canvas/90 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight text-ink">
          Forge<span className="text-accent">X</span>
        </Link>

        <div className="flex items-center gap-3 sm:gap-5">
          <Link
            href="/register"
            className="hidden text-sm font-medium text-ink-muted transition-colors hover:text-ink sm:inline"
          >
            List your company
          </Link>
          <Link
            href="/login"
            className="inline-flex h-9 items-center rounded-md border border-border-strong px-4 text-sm font-medium text-ink transition-colors hover:bg-surface"
          >
            Sign in
          </Link>
        </div>
      </div>
    </header>
  );
}
