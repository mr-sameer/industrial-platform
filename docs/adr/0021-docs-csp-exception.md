# 0021 — Scoped CSP Exception for /docs and /redoc

## Status
Accepted

## Context
Module 2.5's `SecurityHeadersMiddleware` (ADR-0020) applies
`Content-Security-Policy: default-src 'none'` to every response. This
was correct reasoning for a JSON-only API — until it was pointed out
that FastAPI's built-in `/docs` (Swagger UI) and `/redoc` (ReDoc) are
HTML pages that load their actual UI from a CDN
(`cdn.jsdelivr.net`, plus `fastapi.tiangolo.com` for a favicon and
Google Fonts for ReDoc). `default-src 'none'` blocks all of that, so
`/docs` rendered as a blank white page with `swagger-ui-bundle.js`,
`swagger-ui-standalone-preset.js`, and `swagger-ui.css` all blocked by
CSP — a genuine regression, verified by inspecting the exact HTML
FastAPI generates (`fastapi.openapi.docs.get_swagger_ui_html`/
`get_redoc_html`) rather than assumed.

## Decision
`SecurityHeadersMiddleware` now applies one of two CSP values depending
on the request path:

- **`/docs`, `/docs/oauth2-redirect`, `/redoc`** (and only when
  `ENVIRONMENT` is not `production`): a narrowly-scoped policy allowlisting
  exactly the origins those two pages need
  (`cdn.jsdelivr.net`, `fastapi.tiangolo.com`, `fonts.googleapis.com`,
  `fonts.gstatic.com`) — nothing broader.
- **Every other path, and these same paths in production**: the original,
  unchanged `default-src 'none'`.

This is safe in production without any additional guard because
`app.main.create_app` already sets `docs_url`/`redoc_url` to `None` in
production (a Module 1/2 decision, unchanged) — those routes simply
don't exist there, so a path-based CSP exception for them has zero
production attack surface. Verified directly: a live production-mode
server run in this session returns `404` for `/docs` and `/redoc`, still
carrying the strict `default-src 'none'` header.

## Alternatives considered
- **Weaken CSP globally** (e.g. always allow `cdn.jsdelivr.net`):
  rejected — every other endpoint is JSON-only and has no legitimate
  reason to load a script from anywhere, so this would be a strictly
  worse tradeoff for no benefit outside the two doc pages.
- **Self-host swagger-ui-dist/redoc as static assets** (via FastAPI's
  `swagger_js_url`/`swagger_css_url` parameters pointed at a local
  `StaticFiles` mount): the more "correct" long-term fix — it would let
  `/docs` work under the *original* strict CSP (`default-src 'self'`)
  with no CDN exception needed at all, and would also work if docs were
  ever enabled in a non-local non-production environment (e.g. staging).
  Not done here because it's materially more invasive (new dependency,
  new static-file route, asset-version-pinning maintenance) than the
  bug fix warrants — recorded as the natural next step if `/docs` is
  ever needed outside pure local development.

## Consequences
- `/docs` and `/redoc` work again in local development.
- No change to the CSP any other route receives, in any environment.
- If Module 3A+ ever needs `/docs` available in a deployed
  non-production environment (e.g. staging), this same path-based
  exception already covers it — no further change needed, since the
  condition is `ENVIRONMENT != production`, not `ENVIRONMENT ==
  development` specifically.
- The self-hosted-assets alternative above remains available as a
  future improvement if the CDN dependency itself becomes undesirable
  (e.g. for offline development, or to remove the CDN as an external
  trust dependency entirely).
