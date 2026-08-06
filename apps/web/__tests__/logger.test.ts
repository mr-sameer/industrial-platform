import { describe, expect, it } from "vitest";

/**
 * Regression test for the pino-pretty crash: constructing the logger
 * must never throw, in any environment. It previously threw
 * synchronously — "unable to determine transport target for
 * 'pino-pretty'" — because src/lib/logger.ts used pino's `transport`
 * option (which resolves its target via a worker thread, at
 * construction time) pointing at a package that was never installed.
 * The fix removes the `transport` option entirely; pretty-printing is
 * now a local-only concern handled by piping `next dev`'s stdout
 * through the pino-pretty CLI (see package.json's "dev" script), never
 * something the logger module itself does. See src/lib/logger.ts's
 * module docstring for the full root-cause writeup.
 */
describe("logger", () => {
  it("constructs without throwing, and can log without throwing", async () => {
    const { logger } = await import("@/lib/logger");
    expect(() => logger.info("regression test log line")).not.toThrow();
    expect(() => logger.error({ err: new Error("test") }, "regression test error line")).not.toThrow();
  });
});
