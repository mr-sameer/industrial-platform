import pino from "pino";

/**
 * Structured JSON logger for server-side code (route handlers, middleware,
 * server components). Always emits plain NDJSON — see the "why no
 * transport" note below — so log aggregators (e.g. Loki, CloudWatch) can
 * parse it directly in every environment, not just production.
 *
 * Why no `transport` option: pino's `transport: { target: "pino-pretty" }`
 * spawns a worker thread that resolves "pino-pretty" via Node's module
 * resolution *from inside that worker*, synchronously, before the worker
 * even starts — pino does this deliberately, to fail fast with a clear
 * error rather than a confusing worker crash. That's the exact error this
 * used to throw here: "unable to determine transport target for
 * 'pino-pretty'" — because pino-pretty was never installed (verified: not
 * in package.json, not in node_modules, not in the lockfile). Since
 * `export const logger = pino(...)` runs at module-import time, this threw
 * synchronously the instant anything imported this file — which every
 * Company page does (companies/page.tsx → lib/companies.ts →
 * lib/api-client.ts → this file) — before any request-handling code ran,
 * which is why it took down those pages uniformly with a 500.
 *
 * Even with pino-pretty installed, the `transport` worker-thread mechanism
 * is a known source of fragility inside Next.js's server runtime: dev-mode
 * compiler transforms and, worse, `next build`'s file-tracing for
 * `output: "standalone"` (this app's config — see next.config.mjs) both
 * analyze imports statically, and pino's runtime, string-based worker
 * module resolution isn't visible to that analysis. Removing `transport`
 * entirely — rather than just reinstalling pino-pretty — fixes both the
 * immediate crash and that latent fragility at once: this file now has no
 * dependency on pino-pretty in any environment, so nothing about it can
 * ever break dev, Docker, SSR, Server Components, or API routes.
 *
 * Pretty-printing for local development is handled entirely outside this
 * file, as a local-terminal convenience: `pnpm dev` pipes stdout through
 * the pino-pretty CLI binary (see apps/web/package.json's "dev" script) —
 * a separate OS process with zero interaction with Next.js's module graph
 * or bundler. `pino-pretty` is a devDependency for exactly that CLI use
 * and is never imported by application code.
 */
export const logger = pino({
  level: process.env.LOG_LEVEL ?? "info",
  base: { service: "web" },
  timestamp: pino.stdTimeFunctions.isoTime,
});
