# 0028 — Docker's dev Script Must Not Require pino-pretty

## Status
Accepted — critical bugfix, follow-up to [ADR-0027](0027-logger-transport-crash-fix.md).

## Context
ADR-0027 fixed the original crash (`pino`'s `transport` option throwing
at construction because `pino-pretty` wasn't installed) by removing
`transport` entirely and instead having `apps/web/package.json`'s `dev`
script pipe `next dev`'s stdout through the `pino-pretty` CLI binary.

That fix still broke `docker compose up --build`, with:
```
sh: 1: pino-pretty: not found
Error: write EPIPE   (repeated)
```

**Root cause:** `docker compose up --build` auto-merges
`docker-compose.override.yml`, which runs the *dev* path — `apps/web/
Dockerfile.dev` building an image, with the container command
`["pnpm", "--filter", "web", "dev"]`. That resolved to the piped `dev`
script from ADR-0027's fix, so the container's runtime — not just the
image build — depended on `pino-pretty` being resolvable at the moment
`next dev`'s stdout pipe was set up.

Two compounding issues made this fail even though the image itself had
`pino-pretty` correctly installed as a devDependency:
1. `docker-compose.override.yml` mounts a **named volume**
   (`web-node-modules`) over `/repo/apps/web/node_modules` specifically
   so bind-mounting live source code (`./apps/web:/repo/apps/web`)
   doesn't shadow the image's installed dependencies. Docker only
   populates a named volume from the image's contents **the first time
   it's created** — rebuilding the image with `--build` does **not**
   refresh an already-existing volume. A `web-node-modules` volume
   created before `pino-pretty` was added (e.g. during earlier testing
   of ADR-0027's fix) would silently keep shadowing the correctly
   up-to-date image indefinitely.
2. Even independent of that, `sh`'s pipe semantics mean that when the
   right-hand side of a pipe (`pino-pretty`) isn't found, the shell
   prints `sh: pino-pretty: not found` and exits immediately, closing
   the pipe's read end — every subsequent write `next dev` makes to its
   own stdout then fails with `EPIPE`, repeatedly, since Next's dev
   server keeps logging.

Both are real, but the second one alone would have caused this failure
even with a perfectly fresh volume/image — a piped dev script is simply
the wrong shape for a Docker container's primary process, regardless of
whether the piped-to binary happens to be present.

## Decision
`apps/web/package.json`'s `dev` script no longer pipes through anything
— it's plain `next dev -p ${WEB_PORT:-3000}`, exactly as it was before
ADR-0027 first touched it. This is what Docker (`docker-compose.override.yml`'s
`command: ["pnpm", "--filter", "web", "dev"]`) runs, and it now has zero
dependency on `pino-pretty` being present, resolvable, or even
installed, at container runtime.

Pretty-printed local logs are available via a **separate, explicitly
opt-in** script: `pnpm dev:pretty` (`"next dev -p ${WEB_PORT:-3000} |
pino-pretty"`) — for developers running the app directly on their host
machine, outside Docker, who have `pino-pretty` available via the normal
`pnpm install` devDependency and choose to run this script instead of
`pnpm dev`. Docker never runs this script.

`pino-pretty` remains a devDependency (used only by `dev:pretty`, never
by application code — ADR-0027's `transport` removal is unchanged and
still correct) and `docker-compose.override.yml` now documents the
named-volume staleness gotcha directly, so a future dependency change
doesn't silently reproduce this same failure mode.

## Alternatives considered
- **Add a fallback in the `dev` script** (e.g. `next dev | (pino-pretty
  || cat)`) so a missing `pino-pretty` degrades gracefully instead of
  crashing: rejected — still couples Docker's primary process to a pipe
  at all, which is fragile (EPIPE risk if the downstream process ever
  exits for *any* reason, not just "not found") for a purely cosmetic
  feature Docker has no use for in the first place.
- **Install `pino-pretty` in the production image too, "just in case"**:
  rejected — the production Dockerfile never ran a dev script and never
  needed it; this would only reintroduce the dependency ADR-0027
  correctly removed from the production path.

## Verification
No Docker daemon is available in the environment this fix was developed
in, so `docker compose up --build` itself could not be run directly —
stated plainly rather than assumed away. The strongest available
alternative was used instead: the exact `Dockerfile.dev` install
instruction (`pnpm install --filter web...`) was run from a completely
clean, isolated directory containing only the files that Dockerfile
`COPY`s, followed by the exact container command
(`pnpm --filter web dev`) with the real application source overlaid
(matching the override's bind mount). Result: server ready in ~1.8s, no
`pino-pretty` error, no EPIPE, and `/`, `/companies`, `/companies/new`,
and `/companies/search` all returned `200`.

## Consequences
- Docker's dev container now has one fewer moving part (no pipe, no
  dependency on an external CLI binary's presence) in its primary
  process — strictly more robust.
- Anyone wanting colorized local logs outside Docker runs
  `pnpm dev:pretty` instead of `pnpm dev` — an explicit choice, not a
  silent default that Docker also has to satisfy.
- The named-volume staleness gotcha this incident surfaced is now
  documented at the point future maintainers will actually see it
  (`docker-compose.override.yml` itself), reducing the odds of losing
  time to the same failure mode over an unrelated future dependency
  change.
