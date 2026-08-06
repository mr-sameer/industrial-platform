"""
FastAPI application factory and entrypoint.

Run locally with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Run via docker-compose (from repo root):
    docker compose up api
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth import router as auth_router
from app.api.v1.companies import router as companies_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import RateLimitExceededError
from app.core.responses import error_response
from app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger(__name__)
    logger.info(
        "service_starting", environment=settings.environment, version=settings.service_version
    )
    yield
    logger.info("service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Industrial Intelligence Platform API",
        version=settings.service_version,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
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

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_exception_handler(
        _request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        body = error_response(
            code="RATE_LIMITED",
            message=f"Too many requests. Try again in {exc.retry_after_seconds} seconds.",
        )
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
