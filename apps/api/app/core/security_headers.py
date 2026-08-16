"""
Security response headers — see docs/adr/0020-security-headers-and-cors.md.
Applied to every response via BaseHTTPMiddleware. The API serves JSON
only (no HTML), so CSP is intentionally locked down to `default-src 'none'`
— there is nothing here for a browser to render, so no script/style/img
sources need to be allowed.

Exception: FastAPI's /docs and /redoc pages are HTML that needs to load
JS/CSS to render. Module 2.5 originally allowed this via CDN origins
(cdn.jsdelivr.net, fonts.googleapis.com, etc.); that was replaced with
fully self-hosted assets (docs/adr/0034-self-hosted-api-docs.md) after
a real, confirmed bug: this sandbox's network egress policy returns a
403 for cdn.jsdelivr.net, so the CDN-allowlisted CSP was necessary but
not sufficient — /docs returned 200 while Swagger UI never actually
rendered. Now that every asset those two pages need is served from
this same origin, no external domain needs allowlisting at all —
'self' covers every JS/CSS/image/font load. 'unsafe-inline' on
script-src is still needed, though: FastAPI's get_swagger_ui_html/
get_redoc_html output embeds an inline <script> that actually calls
SwaggerUIBundle(...)/Redoc.init(...) to initialize the UI, not just
references to the external JS files — confirmed via real headless-
browser testing (Playwright), not assumed: with script-src 'self'
alone, the JS bundle loaded (200) but the page rendered completely
blank (0 bytes of visible content) because the initialization script
itself was blocked. Scoped to docs-only and dev-only (docs_url=None in
production, so this CSP value is never even reachable there) — the
same narrowly-scoped dev-only relaxation pattern already established
for the frontend's own CSP (see the web app's middleware.ts and
docs/adr/0031).

Two more real findings from the same real-browser testing pass:
`worker-src 'self' blob:` is needed because ReDoc spins up a Web
Worker from a `blob:` URL internally (search indexing) — with no
`worker-src` directive, CSP falls back to `script-src`, which doesn't
include `blob:`. Separately, `redoc.standalone.js` also tries to fetch
`https://cdn.redoc.ly/redoc/logo-mini.svg` — its own hardcoded default
branding image, not something in this app's HTML template — which is
deliberately left blocked: it's a purely cosmetic image ReDoc degrades
gracefully without (confirmed: the page renders fully functional
either way), and allowlisting `cdn.redoc.ly` would reintroduce exactly
the kind of external-network dependency this entire self-hosting
effort exists to eliminate.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

settings = get_settings()

# Exact paths FastAPI serves its own docs UI from, plus the static
# asset mounts those pages load from (docs/redoc "assets" prefixes,
# app.main.create_app) — /docs/oauth2-redirect is included for
# completeness (used only if OAuth2 login is configured in Swagger UI,
# which this API doesn't do today, but costs nothing to cover now).
_API_DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})
_API_DOCS_PREFIXES = ("/docs/assets/", "/redoc/assets/")

# Every asset /docs and /redoc need is now served from this same origin
# (see this module's docstring) — no external domain needs allowlisting
# at all. 'unsafe-inline' for style-src is Swagger UI/ReDoc's own
# inline styles, not anything this app authors.
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'"
)

_LOCKED_DOWN_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        is_docs_request = request.url.path in _API_DOCS_PATHS or request.url.path.startswith(
            _API_DOCS_PREFIXES
        )
        if is_docs_request and not settings.is_production:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = _LOCKED_DOWN_CSP

        if settings.is_production:
            # Only meaningful over HTTPS, which is what production is expected to run under.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
