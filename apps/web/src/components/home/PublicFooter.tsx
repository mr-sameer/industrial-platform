import Link from "next/link";

/**
 * Drastically simplified — no multi-column link farm (the previous
 * version's "Discover"/"Platform" columns pointed at nav items and
 * anchors that no longer exist). Only real destinations: logo, List
 * Your Company, Sign in, copyright.
 */
export function PublicFooter() {
  return (
    <footer className="border-t border-border bg-canvas px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-4 text-center sm:flex-row sm:justify-between sm:text-left">
        <div>
          <span className="font-display text-base font-semibold text-ink">
            Forge<span className="text-accent">X</span>
          </span>
          <span className="ml-2 text-xs text-ink-faint">AI-Powered Industrial Intelligence Platform</span>
        </div>
        <div className="flex items-center gap-5 text-sm text-ink-muted">
          <Link href="/register" className="hover:text-ink">
            List your company
          </Link>
          <Link href="/login" className="hover:text-ink">
            Sign in
          </Link>
          <span className="text-xs text-ink-faint">© {new Date().getFullYear()} Nexora Intelligence</span>
        </div>
      </div>
    </footer>
  );
}
