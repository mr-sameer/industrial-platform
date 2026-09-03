"""
FastAPI application factory and entrypoint.

Run locally with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Run via docker-compose (from repo root):
    docker compose up api
"""

import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.acquisition import router as acquisition_router
from app.api.v1.acquisition_review import router as acquisition_review_router
from app.api.v1.auth import router as auth_router
from app.api.v1.companies import router as companies_router
from app.api.v1.company_verification import router as company_verification_router
from app.api.v1.data_quality import router as data_quality_router
from app.api.v1.entity_resolution import router as entity_resolution_router
from app.api.v1.graph import router as graph_router
from app.api.v1.health import router as health_router
from app.api.v1.offerings import router as offerings_router
from app.api.v1.product_attribute_evidence import router as product_attribute_evidence_router
from app.api.v1.products import categories_router
from app.api.v1.products import router as products_router
from app.api.v1.provenance import router as provenance_router
from app.api.v1.provenance import sources_router
from app.api.v1.requirements import router as requirements_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import RateLimitExceededError
from app.core.responses import error_response
from app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()


def _redact_database_url(url: str) -> str:
    """Password-masked DATABASE_URL, safe to log/print."""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


class DatabaseStartupError(RuntimeError):
    """Raised when the app cannot reach Postgres with the resolved
    DATABASE_URL — see the loud, actionable message this constructs
    below. Deliberately a distinct exception type, not left as a raw
    asyncpg traceback: the previous behavior was that a broken DB
    connection surfaced only on the *first request that touched it*
    (e.g. registration), deep inside a stack trace with no indication
    of which DATABASE_URL was actually in play — confirmed as a real
    diagnosability gap, not a hypothetical one, after a reported
    'role "platform_user" does not exist' error that this exact check
    would have caught immediately, loudly, at startup instead."""


def _parse_database_url(url: str) -> dict[str, str]:
    match = re.match(r"postgresql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+):(\d+)/(\w+)", url)
    if not match:
        raise ValueError(f"Could not parse DATABASE_URL: {_redact_database_url(url)}")
    user, password, host, port, dbname = match.groups()
    return {"user": user, "password": password, "host": host, "port": port, "dbname": dbname}


async def _try_auto_create_role_and_database(parsed: dict[str, str]) -> bool:
    """
    Automatically creates the missing role/database that
    _verify_database_connection's primary connection attempt just
    failed to reach — no manual step required, per this exact
    situation's own report ("do not tell me to run bootstrap
    manually"). Mirrors scripts/bootstrap_local_postgres.sh's logic,
    but runs inline, automatically, at the moment the app actually
    needs it, rather than depending on a separate step someone has to
    remember (or that could target a different Postgres instance than
    the one DATABASE_URL actually points at — the exact ambiguity this
    inline approach eliminates by construction: whatever server this
    process can reach IS the one being fixed).

    Only ever attempted for a local target (127.0.0.1/localhost) and
    only outside production — this connects as whatever OS user is
    already running this process, via the Postgres default database
    and peer/trust auth on the loopback/local connection, which is
    either already permitted (typical local dev Postgres install) or
    fails cleanly and this function returns False without side effects.
    Never attempts to escalate privileges this process doesn't already
    have.
    """
    if settings.is_production:
        return False
    if parsed["host"] not in ("localhost", "127.0.0.1"):
        return False

    logger = get_logger(__name__)
    try:
        # No host= passed: asyncpg then connects via the local Unix
        # socket, not TCP — this distinction matters. A typical local
        # Postgres install's pg_hba.conf allows peer auth (no password)
        # for Unix-socket connections specifically, while still
        # requiring a password over TCP/127.0.0.1 even for local
        # traffic — confirmed directly against this sandbox's own
        # pg_hba.conf, not assumed. Connecting with host="localhost"
        # (TCP) would always hit the password rule regardless of
        # OS-level privileges, making this auto-fix attempt pointless.
        admin_conn = await asyncpg.connect(database="postgres", timeout=5)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any failure here just means "can't auto-fix", not a crash
        print(f"[startup] Automatic role creation not possible: {exc}")
        return False

    try:
        role_exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", parsed["user"]
        )
        if not role_exists:
            print(f"[startup] Auto-creating missing role {parsed['user']!r}...")
            await admin_conn.execute(
                f'CREATE ROLE "{parsed["user"]}" WITH LOGIN SUPERUSER '
                f"PASSWORD '{parsed['password']}'"
            )
            logger.info("database_auto_created_role", role=parsed["user"])

        db_exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", parsed["dbname"]
        )
        if not db_exists:
            print(f"[startup] Auto-creating missing database {parsed['dbname']!r}...")
            await admin_conn.execute(
                f'CREATE DATABASE "{parsed["dbname"]}" OWNER "{parsed["user"]}"'
            )
            logger.info("database_auto_created_database", database=parsed["dbname"])

        return True
    except Exception as exc:  # noqa: BLE001 — same reasoning as above
        print(f"[startup] Automatic role/database creation failed: {exc}")
        return False
    finally:
        await admin_conn.close()


async def _verify_database_connection() -> None:
    redacted = _redact_database_url(settings.database_url)
    logger = get_logger(__name__)
    logger.info("database_connection_check_starting", database_url=redacted)
    # Deliberately printed too, not just logged — structlog's output
    # may be JSON-formatted (production) or otherwise easy to miss in
    # a scrollback; this specific line is meant to be unmissable when
    # debugging exactly this class of problem, on any machine.
    print(f"[startup] Connecting to database: {redacted}")

    # asyncpg directly (bypassing the SQLAlchemy pool) so this check is
    # a single, immediate, unambiguous connection attempt — not
    # dependent on pool lazy-initialization timing.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        conn = await asyncpg.connect(dsn, timeout=5)
    except (
        asyncpg.InvalidAuthorizationSpecificationError,
        asyncpg.InvalidPasswordError,
        asyncpg.InvalidCatalogNameError,
    ) as exc:
        auto_fixed = False
        try:
            parsed = _parse_database_url(settings.database_url)
            auto_fixed = await _try_auto_create_role_and_database(parsed)
        except ValueError:
            pass  # couldn't parse DATABASE_URL — fall through to the manual-diagnosis message below

        last_error: BaseException = exc
        if auto_fixed:
            print("[startup] Retrying the original connection after automatic setup...")
            try:
                conn = await asyncpg.connect(dsn, timeout=5)
            except Exception as retry_exc:  # noqa: BLE001 — fall through to the detailed error below either way
                last_error = retry_exc
            else:
                server_version, current_db, current_user = await conn.fetchrow(
                    "SELECT current_setting('server_version'), current_database(), current_user"
                )
                await conn.close()
                logger.info(
                    "database_connection_check_passed_after_auto_fix",
                    server_version=server_version,
                    database=current_db,
                    role=current_user,
                )
                print(
                    f"[startup] Connected OK after automatic fix — database={current_db!r} "
                    f"role={current_user!r} postgres={server_version}"
                )
                return

        raise DatabaseStartupError(
            f"\n\n"
            f"{'=' * 78}\n"
            f"DATABASE STARTUP CHECK FAILED\n"
            f"{'=' * 78}\n"
            f"Connecting to: {redacted}\n"
            f"Postgres says: {last_error}\n\n"
            f"Automatic role/database creation was attempted and did not succeed\n"
            f"(see the [startup] lines above for why). This means either the role\n"
            f"in DATABASE_URL doesn't exist on the Postgres server this app is\n"
            f"actually connecting to, or it exists with a different password than\n"
            f"DATABASE_URL has. Common causes:\n"
            f"  1. More than one Postgres instance is installed/running on this\n"
            f"     machine (e.g. a native install AND Docker's postgres container),\n"
            f"     and this app is reaching a different one than you expect.\n"
            f"     Check what's actually listening: `lsof -i :5432` or\n"
            f"     `pg_lsclusters` (Debian/Ubuntu) to see every local instance.\n"
            f"  2. PGHOST/PGPORT/PGUSER/PGPASSWORD are set in your shell profile\n"
            f"     and are overriding what you think DATABASE_URL controls.\n"
            f"     Check: `env | grep '^PG'`\n"
            f"  3. This process's OS user doesn't have local-superuser access to\n"
            f"     Postgres (peer/trust auth), so automatic creation couldn't\n"
            f"     connect at all — run scripts/bootstrap_local_postgres.sh as a\n"
            f"     user that does (e.g. the `postgres` OS user), or set\n"
            f"     DATABASE_URL to a role that already exists on this server.\n"
            f"{'=' * 78}\n"
        ) from last_error
    except (OSError, asyncpg.PostgresConnectionError) as exc:
        raise DatabaseStartupError(
            f"\n\n"
            f"{'=' * 78}\n"
            f"DATABASE STARTUP CHECK FAILED — cannot reach the server at all\n"
            f"{'=' * 78}\n"
            f"Connecting to: {redacted}\n"
            f"Error: {exc}\n\n"
            f"Is Postgres actually running and listening on that host/port?\n"
            f"{'=' * 78}\n"
        ) from exc
    else:
        server_version, current_db, current_user = await conn.fetchrow(
            "SELECT current_setting('server_version'), current_database(), current_user"
        )
        await conn.close()
        logger.info(
            "database_connection_check_passed",
            server_version=server_version,
            database=current_db,
            role=current_user,
        )
        print(
            f"[startup] Connected OK — database={current_db!r} role={current_user!r} "
            f"postgres={server_version}"
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger(__name__)
    logger.info(
        "service_starting", environment=settings.environment, version=settings.service_version
    )
    await _verify_database_connection()
    yield
    logger.info("service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ForgeX API",
        version=settings.service_version,
        lifespan=lifespan,
        # Disabled here, not left as FastAPI's default — the default
        # /docs and /redoc HTML hardcodes CDN URLs
        # (cdn.jsdelivr.net). Custom routes below serve the same UI
        # from locally-vendored/installed assets instead — see
        # docs/adr/0034-self-hosted-api-docs.md for why: this sandbox's
        # network egress policy returns a real 403 for
        # cdn.jsdelivr.net, so /docs previously returned 200 (the HTML
        # shell loaded fine) while the actual Swagger UI never
        # rendered — a real, confirmed bug, not a hypothetical one.
        docs_url=None,
        redoc_url=None,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(health_router)  # unversioned alias: GET /health
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(companies_router, prefix="/api/v1")
    app.include_router(company_verification_router, prefix="/api/v1")
    app.include_router(offerings_router, prefix="/api/v1")
    app.include_router(products_router, prefix="/api/v1")
    app.include_router(categories_router, prefix="/api/v1")
    app.include_router(product_attribute_evidence_router, prefix="/api/v1")
    app.include_router(provenance_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(acquisition_router, prefix="/api/v1")
    app.include_router(acquisition_review_router, prefix="/api/v1")
    app.include_router(entity_resolution_router, prefix="/api/v1")
    app.include_router(data_quality_router, prefix="/api/v1")
    app.include_router(graph_router, prefix="/api/v1")
    app.include_router(requirements_router, prefix="/api/v1")

    # Serves whatever app.core.storage.LocalStorageBackend writes — see
    # that module's docstring. os.makedirs guards against a fresh
    # checkout/container where the directory doesn't exist yet; mounting
    # a StaticFiles instance over a nonexistent directory raises at
    # startup, which would be a needlessly bad first-run experience.
    os.makedirs(settings.upload_storage_path, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_storage_path), name="uploads")

    # Self-hosted API docs — see the FastAPI(...) docs_url=None comment
    # above for why. Never registered in production, matching the
    # previous docs_url/redoc_url conditional exactly (is_production
    # still means no docs routes exist at all).
    if not settings.is_production:
        _swagger_ui_static_dir = os.path.join(os.path.dirname(__file__), "static", "swagger-ui")
        app.mount(
            "/docs/assets", StaticFiles(directory=_swagger_ui_static_dir), name="swagger-ui-assets"
        )
        _redoc_static_dir = os.path.join(os.path.dirname(__file__), "static", "redoc")
        app.mount("/redoc/assets", StaticFiles(directory=_redoc_static_dir), name="redoc-assets")

        @app.get("/docs", include_in_schema=False)
        async def custom_swagger_ui_html() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=app.openapi_url or "/openapi.json",
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url="/docs/oauth2-redirect",
                swagger_js_url="/docs/assets/swagger-ui-bundle.js",
                swagger_css_url="/docs/assets/swagger-ui.css",
                swagger_favicon_url="/docs/assets/favicon-32x32.png",
            )

        @app.get("/docs/oauth2-redirect", include_in_schema=False)
        async def swagger_ui_redirect() -> HTMLResponse:
            return get_swagger_ui_oauth2_redirect_html()

        @app.get("/redoc", include_in_schema=False)
        async def custom_redoc_html() -> HTMLResponse:
            return get_redoc_html(
                openapi_url=app.openapi_url or "/openapi.json",
                title=f"{app.title} - ReDoc",
                redoc_js_url="/redoc/assets/redoc.standalone.js",
                redoc_favicon_url="/docs/assets/favicon-32x32.png",
                with_google_fonts=False,  # fonts.googleapis.com is also an external CDN — same fix, same reason
            )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_exception_handler(
        _request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        message = f"Too many requests. Try again in {exc.retry_after_seconds} seconds."
        if not settings.is_production:
            # Purely a message-text addition — the limit itself is
            # identical in every environment; this only ever changes
            # what the response *says*, never whether or how strictly
            # it's enforced. See docs/adr/0036-dev-rate-limit-reset-workflow.md
            # for why local dev legitimately exhausts real, unweakened
            # limits faster than a real deployment would.
            message += (
                " (Local development: run `make reset-rate-limit` from the repo root, "
                "or `bash scripts/reset_dev_rate_limits.sh` from apps/api, to clear "
                "only the auth rate-limit keys — see docs/adr/0036.)"
            )
        body = error_response(code="RATE_LIMITED", message=message)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=body.model_dump(),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic v2 includes the raw exception instance in error['ctx']['error']
        # when a @field_validator raises a plain ValueError (e.g.
        # CompanyMemberCreate's "cannot invite as Owner" check) — not
        # JSON-serializable via the stdlib json module used by JSONResponse.
        # jsonable_encoder converts it (and anything else non-serializable)
        # to a safe representation. This was a latent bug since Module 1/2 —
        # never triggered before because no earlier test exercised a
        # field_validator-raised ValueError all the way to this handler.
        safe_errors = jsonable_encoder(exc.errors())
        first_error = safe_errors[0] if safe_errors else {}
        field = ".".join(str(p) for p in first_error.get("loc", [])) or None
        body = error_response(
            code="VALIDATION_ERROR",
            message=first_error.get("msg", "Invalid request payload."),
            field=field,
            details=safe_errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump()
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Routes that need a stable, specific error code (e.g. app/api/v1/auth.py)
        # raise HTTPException(detail={"code": "...", "message": "..."}) — honor
        # that shape here; fall back to a generic HTTP_<status> code otherwise.
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            body = error_response(code=exc.detail["code"], message=exc.detail["message"])
        else:
            body = error_response(code=f"HTTP_{exc.status_code}", message=str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        get_logger(__name__).error("unhandled_exception", error=str(exc), exc_info=True)
        body = error_response(code="INTERNAL_SERVER_ERROR", message="An unexpected error occurred.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump()
        )

    return app


app = create_app()
