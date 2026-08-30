/**
 * ForgeX Product Audit P1 #6: nav clicks (Companies, "Create your first
 * company", etc.) previously gave zero visual feedback for the 1-4s a
 * client-side route transition can take in this app (RSC payload fetch
 * + dev-mode on-demand compilation) — the old page just sat there
 * unchanged, which the audit's own live testing read as the click
 * having silently failed, prompting a second click. Next.js renders
 * this automatically as the `{children}` fallback in
 * `(app)/layout.tsx` during exactly that gap — AppShell's sidebar/top
 * bar never unmount, only the content area shows this, matching the
 * same spinner AppShell itself uses for the initial auth-bootstrap
 * load.
 */
export default function AppRouteGroupLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
    </div>
  );
}
