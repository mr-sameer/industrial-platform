# 0031 — Fix: CSP Blocked Hydration, Backend Calls, and Docker's Build-Time API URL

## Status
Accepted — critical bugfix, found via real-browser (Playwright/Chromium)
investigation. Every prior verification of this frontend, across every
module, used `curl` — which doesn't execute JavaScript and so never
exercised any of these bugs. This is the first time this project's
frontend was actually tested in a real browser.

## Context
Phase 1 was rejected on manual browser testing: `/login` and `/register`
rendered unstyled, and `/companies` hung on a loading spinner forever.
Investigated with a real headless Chromium (Playwright, already present
in this sandbox) driving the actual app — console errors, network
traces, and screenshots, not curl.

## Root causes (five, compounding)

**1. CSP blocked React hydration entirely, on every page.** The
original CSP (Module 2.5): `script-src 'self'` — no nonce, no
`unsafe-inline`. Next.js's App Router always injects inline `<script>`
tags carrying the RSC/hydration payload; this is the framework's own
internal mechanism, not something avoiding inline scripts in
application code sidesteps. Confirmed via console:
`Refused to execute inline script... Content Security Policy`. With
hydration blocked, React never mounts client-side — every client
component (`AuthContext`, `AppShell`, `CommandSearch`) is dead on
arrival, and any page whose content depends on client state (like
`AppShell`'s auth-gated loading spinner) is stuck exactly at its
server-rendered pre-hydration state forever. This is the direct, full
explanation for "/companies stuck loading forever."

**2. CSP's `connect-src 'self'` blocked every client-side call to the
FastAPI backend.** Confirmed via console:
`Refused to connect to 'http://...:8000/api/v1/companies'... connect-src 'self'`.
Module 3A/3B's frontend code calls the backend directly (a different
origin from the Next.js app) — `'self'` alone blocks all of it.
`img-src` had the identical problem for Module 3B's uploaded
logo/cover images, served from the same backend origin.

**3. `'strict-dynamic'` (the first fix attempt) disabled `'self'`
entirely.** Per the CSP3 spec, when `'strict-dynamic'` is present,
host-based allowlisting (`'self'`, etc.) is ignored for script-src.
Confirmed via a second round of real production-build testing: every
same-origin `<script src="/_next/static/...">` chunk tag was refused,
even though `'self'` was also listed. Removed `'strict-dynamic'` — this
app is same-origin only (no third-party script loading, which is
`'strict-dynamic'`'s actual use case), so plain `'self'` + nonce is
correct and sufficient.

**4. Statically-generated pages can never receive a per-request
nonce.** Even after fixing 1–3, inline scripts were *still* blocked in
a production build specifically — confirmed via real testing. Root
cause: `/login` and `/register` were statically prerendered (`○` in the
build output) — their HTML, including any inline scripts, is fixed at
*build* time. There is no per-request opportunity to embed a nonce that
matches whatever middleware puts in that request's CSP header, because
the HTML was already generated before any request existed. This is a
documented Next.js constraint, not a bug workaround: nonce-based CSP
requires dynamic rendering. Fixed with `export const dynamic =
"force-dynamic"` in the root layout, applying to the whole app.

**5. React 18 StrictMode's dev-mode double-effect-invocation hit
refresh-token reuse detection.** Confirmed via network trace: two
`/api/auth/refresh` calls on mount, first `200`, second `401`. Refresh
tokens rotate on every use (Module 2.5) — the second call, using a
token the first call already consumed, was correctly flagged as
reuse and the session likely revoked. Only affects `next dev` (and
therefore `docker compose up`'s default dev path) — StrictMode's
double-invocation doesn't happen in production builds at all. Fixed
with a `useRef` guard in `AuthContext`'s bootstrap effect, ensuring the
actual network call fires once regardless of how many times the effect
itself runs.

**A sixth, related but separate finding**, surfaced while confirming
fix #2 held in a real production Docker-equivalent build:
`NEXT_PUBLIC_API_BASE_URL` was only ever set in `docker-compose.yml`'s
*runtime* `environment:` block. `NEXT_PUBLIC_*` variables are inlined
into the client JavaScript bundle at **build** time — a runtime-only
value has no effect on the already-built client code, which would keep
whatever value (or lack of one) was present during `docker build`. This
produces exactly the class of bug fix #2 addresses, from a different
angle: the client bundle and the server-side CSP (which correctly reads
the runtime value) disagreeing about the API's origin. Fixed by
accepting `NEXT_PUBLIC_API_BASE_URL` as a Docker build `ARG` in
`apps/web/Dockerfile`, and passing it as a build `arg` in
`docker-compose.yml`'s `web` service — set to the exact same value as
the runtime `environment:` entry, so client and server can never
disagree.

## A genuine false positive, also fixed while investigating
A React hydration-mismatch warning on the login form's email/password
inputs (`style` attribute differed between "server" and "client").
Traced to Chromium's own autofill/password-manager heuristics mutating
input attributes before React's hydration check runs — a well-
documented, harmless false-positive class, not an app bug. Mitigated
with `suppressHydrationWarning` on the affected inputs, the standard
recommended approach.

## Verification
- Real headless Chromium (Playwright) driving the actual app — not
  curl — for every fix, both in `next dev` (matching `docker compose
  up`'s default path) and in a real `next build` + `next start`
  production build with a correctly build-time-consistent
  `NEXT_PUBLIC_API_BASE_URL`.
- Full register → redirect-to-dashboard → navigate-to-`/companies` flow,
  confirmed with **zero console errors and zero page errors** in both
  dev and production mode, screenshots captured at each step.
- Screenshots confirm: `/login` and `/register` fully styled (restyled
  with the Phase 1 design system as part of this fix, using the shared
  `Input`/`Button`/`AuthCard` components — they still used Module 2's
  original inline styles before this), `/companies` renders the
  complete `AppShell` (sidebar, active nav state, breadcrumbs, profile
  menu with real user data, footer) with real company data, and the
  ⌘K command palette opens and functions correctly.
- A real, computed CSS property (`getComputedStyle` on the login
  button) was checked, not just class-name presence in HTML — confirmed
  `rgb(47, 111, 238)`, exactly the design system's "Blueprint Blue"
  accent token — concrete proof Tailwind is genuinely applying styles,
  not just present-but-inert in the bundle.
- Full existing test suite (backend 113/118 depending on skip, web 8)
  re-run after all changes — no regressions.

## Consequences
- The whole app is now dynamically rendered (`force-dynamic`), trading
  away static-generation's build-time pre-rendering for the correctness
  nonce-based CSP requires. Acceptable: this app is inherently
  per-user/authenticated for nearly every page; static generation's
  benefit here was always marginal.
- Any future environment variable read by both client code and
  `middleware.ts` needs the same build-time/runtime consistency
  discipline this ADR's sixth finding surfaced — worth a quick audit if
  another `NEXT_PUBLIC_*` variable is ever added.
- This investigation is the first real-browser test of this frontend in
  the project's history. Worth treating as a permanent process change,
  not a one-time fix: a real browser check (this sandbox has Playwright
  and Chromium already available) should be part of verifying any
  future frontend change that touches CSP, auth bootstrap, or hydration
  — `curl`-only verification cannot catch any of these five bug
  classes, by construction.
