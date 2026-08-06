# 0012 — Web Session Strategy: BFF Pattern with httpOnly Refresh Cookie

## Status
Accepted

## Context
The API (`localhost:8000`) and web app (`localhost:3000`) are different
origins. A refresh token set as a cookie directly by the API would either
need `SameSite=None; Secure` cross-site cookies (fragile, blocked by some
browser privacy modes, and still exposes the long-lived token to any XSS
on the web app if also readable by JS) or a same-origin reverse proxy.
We also don't want the long-lived refresh token reachable by JavaScript
at all, to limit XSS blast radius.

## Decision
Next.js Route Handlers under `apps/web/src/app/api/auth/*` act as a thin
**Backend-for-Frontend (BFF)**:

- The browser only ever calls `apps/web`'s own `/api/auth/*` routes, never
  the FastAPI service directly, for anything auth-related.
- Those route handlers call the FastAPI `/api/v1/auth/*` endpoints
  server-side (server-to-server, no CORS/cookie complications).
- On login/register/refresh, the route handler sets the **refresh token**
  as an `httpOnly`, `Secure` (in production), `SameSite=Lax` cookie
  scoped to the web app's own domain (`apps/web/src/lib/auth/cookies.ts`),
  and returns only the **access token** in the JSON body for short-lived,
  in-memory client-side storage (`apps/web/src/lib/auth/token-store.ts`).
- `apps/web/src/middleware.ts` checks for the presence of that cookie to
  redirect unauthenticated requests away from protected routes — a
  cheap, non-cryptographic gate; the API is still the source of truth
  and re-validates the access token on every request.

## Alternatives considered
- **Browser calls the API directly, stores both tokens in
  `localStorage`**: rejected — `localStorage` is readable by any script
  on the page, making XSS trivially exfiltrate both tokens with no
  mitigation.
- **API sets cross-site cookies directly (`SameSite=None; Secure`)**:
  works but couples the API's cookie config to every frontend's domain,
  complicates local development (`Secure` cookies need HTTPS), and still
  doesn't solve XSS exposure unless also marked `httpOnly` — at which
  point a BFF is doing the same job with less cross-site fragility.
- **Full reverse proxy (e.g. web app proxies literally all `/api/*`
  traffic to FastAPI)**: viable and arguably simpler long-term, but a
  bigger structural change than Module 2's auth-only scope calls for.
  Revisit if BFF route handlers proliferate beyond auth.

## Consequences
- The access token lives only in browser memory (React context/state) and
  is lost on full page reload — the web app must call `POST
  /api/auth/refresh` (which reads the httpOnly cookie server-side) on
  app bootstrap to re-establish a session silently.
- Mobile does **not** use this pattern — it calls the FastAPI
  `/api/v1/auth/*` endpoints directly and stores both tokens in platform
  secure storage (Keychain/Keystore via `flutter_secure_storage`), since
  a native app has no equivalent XSS threat model and no cross-origin
  cookie problem to solve.
- `NEXT_PUBLIC_API_BASE_URL` is used by the BFF route handlers
  server-side; it is **not** used by any client component for
  auth-related calls, which all go through `/api/auth/*` instead.
