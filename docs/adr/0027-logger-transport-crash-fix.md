# 0027 — Fix: Remove pino's `transport` Option to Stop the pino-pretty Crash

## Status
Superseded by [ADR-0028](0028-docker-dev-script-must-not-require-pino-pretty.md).
The `transport`-removal decision below still stands and is unchanged —
but this ADR's follow-up ("pretty-printing via `pnpm dev` piping
through the `pino-pretty` CLI") turned out to still make Docker's dev
container depend on `pino-pretty` being resolvable at container
runtime, which broke in practice. Kept for historical context.

## Context
Every Company page returned HTTP 500 with the error `unable to
determine transport target for "pino-pretty"`, originating in
`apps/web/src/lib/logger.ts`. Reproduced directly in plain Node (no
Next.js involved): `pino({ transport: { target: "pino-pretty" } })`
throws **synchronously, at construction time**, because `pino-pretty`
was never installed — confirmed absent from `package.json`,
`node_modules`, and the lockfile.

Since `export const logger = pino({...})` runs at module-import time,
and every Company page's import chain bottoms out at this file
(`companies/page.tsx` → `lib/companies.ts` → `lib/api-client.ts` →
`lib/logger.ts`), the throw happened before any request-handling code
ran at all — which is why it took down every Company page uniformly,
with the exact stack trace reported.

This only fired when `NODE_ENV === "development"` (the ternary
`logger.ts` used to gate the `transport` option), which is why it
reproduced in local dev / `pnpm dev` rather than a `next build`/`next
start` production run.

## Decision
Removed the `transport` option from `logger.ts` entirely. The logger
now always emits plain NDJSON, in every environment — matching the
file's own original stated intent for production, just applied
unconditionally rather than only there. Pretty-printing for local
development is now a purely external, local-terminal concern: `pnpm
dev` pipes `next dev`'s stdout through the `pino-pretty` CLI binary
(`"dev": "next dev -p ${WEB_PORT:-3000} | pino-pretty"`), added as a
devDependency for exactly that use. No application code imports
`pino-pretty` anywhere, in any environment.

## Why not just install pino-pretty and keep `transport`
Installing the missing dependency would have fixed the immediate crash,
but `transport` fundamentally works by spawning a worker thread that
resolves its target module string *at runtime*, invisible to static
bundling/tracing analysis. That's a poor fit for Next.js specifically:
dev-mode compiler transforms and, more importantly, `next build`'s
file-tracing for `output: "standalone"` (this app's config) both reason
about imports statically. Keeping `transport` would leave a latent risk
that pino-pretty's files simply aren't present in a traced/standalone
Docker output even though it "worked" in a bare `next dev` — the same
class of environment-dependent bug this report was raised about,
just relocated rather than fixed. Removing `transport` eliminates the
entire class of risk, not just today's instance of it.

## Verification (not just fixed and assumed)
- Reproduced the exact crash directly in Node before fixing, confirming
  root cause precisely (not guessed).
- Confirmed the fixed logger constructs and logs without throwing, both
  standalone and via the pino-pretty CLI (which correctly prettifies
  JSON lines and passes non-JSON lines through unchanged — verified
  directly, since `next dev`'s own framework output is not
  pino-formatted).
- Ran a full `pnpm build` — succeeds, and the build's own prerendering
  step emits a real plain-JSON log line from this exact logger,
  confirming the fix holds during actual Next.js build execution.
- Started the **exact standalone `server.js` Docker runs**
  (`apps/web/.next/standalone/apps/web/server.js`) and requested
  `/companies`, `/companies/new`, `/companies/search`, and
  `/company/[slug]` — all returned `200` (the last returning a page
  that gracefully handled a backend-connection failure and logged it as
  clean structured JSON, rather than crashing).
- `tsc --noEmit`, ESLint, and the full Vitest suite (8/8, including a
  new regression test asserting logger construction/logging never
  throws) all pass.
- Confirmed both `apps/web/Dockerfile` (production) and
  `apps/web/Dockerfile.dev` (dev) require no changes: production never
  references `pino-pretty` at all now; dev's `pnpm install
  --filter web...` already installs devDependencies, so the CLI binary
  is present for the piped `dev` script.

## Consequences
- SSR, Server Components, API routes, and middleware all use the same
  unconditional plain-JSON logger — no environment-specific branching
  left in `logger.ts` to get wrong again.
- Local developers get pretty output via the `dev` script's pipe, not
  via any in-process code path — this is strictly safer against future
  bundler/runtime incompatibilities than any conditional-import
  alternative would have been.
- Anyone reading raw NDJSON logs during local development instead of
  running `pnpm dev` (e.g. running `next dev` directly) will see plain
  JSON, not colorized output — an acceptable, documented tradeoff for a
  local-only convenience feature.
