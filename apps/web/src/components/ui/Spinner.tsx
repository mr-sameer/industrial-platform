import { cn } from "@/lib/cn";

/** Shared spinner — same visual AppShell already uses for its own auth-bootstrap/route-transition states, so every "something is loading" moment in the app reads as one calm, consistent signal instead of plain "Loading…" text. */
export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={cn("h-8 w-8 animate-spin rounded-full border-2 border-border-strong border-t-accent", className)}
      role="status"
      aria-label="Loading"
    />
  );
}

/** Full-page centered loading state — the standard replacement for a page's early-return "Loading…" branch. */
export function PageLoading() {
  return (
    <main className="flex min-h-[50vh] items-center justify-center">
      <Spinner />
    </main>
  );
}
