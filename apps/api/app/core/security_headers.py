"""
Security response headers — see docs/adr/0020-security-headers-and-cors.md.
Applied to every response via BaseHTTPMiddleware. The API serves JSON
only (no HTML), so CSP is intentionally locked down to `default-src 'none'`
— there is nothing here for a browser to render, so no script/style/img
sources need to be allowed.

Exception: FastAPI's built-in /docs and /redoc pages are HTML that loads
its actual UI (JS/CSS) from a CDN (cdn.jsdelivr.net, plus
fastapi.tiangolo.com for a favicon and fonts.googleapis.com/
fonts.gstatic.com for ReDoc's fonts) — `default-src 'none'` blocks all of
that, leaving a blank page. Rather than weakening CSP globally, those two
paths get a narrowly-scoped policy allowing exactly those origins, and
only when `docs_url`/`redoc_url` actually exist — i.e. never in
production, where `app.main.create_app` already sets both to `None`
(so `/docs` and `/redoc` 404 before this middleware is even relevant).
This was a genuine regression introduced when this CSP was added in
Module 2.5 — flagged and fixed here rather than silently left broken.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

settings = get_settings()

# Exact paths FastAPI serves its own docs UI from. /docs/oauth2-redirect
# is included for completeness (used only if OAuth2 login is configured
# in Swagger UI, which this API doesn't do today, but costs nothing to
# cover now).
_API_DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})

# The exact external origins FastAPI's default /docs and /redoc HTML
# references — verified directly against the installed fastapi version's
# fastapi.openapi.docs.get_swagger_ui_html / get_redoc_html output, not
# guessed. Nothing broader than this is allowlisted.
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
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

        is_docs_request = request.url.path in _API_DOCS_PATHS
        if is_docs_request and not settings.is_production:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = _LOCKED_DOWN_CSP

        if settings.is_production:
            # Only meaningful over HTTPS, which is what production is expected to run under.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
