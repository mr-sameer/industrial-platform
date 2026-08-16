"""
GET /api/v1/health

Aggregates database and Redis probes into a single response matching
HealthCheckResponse / the shared HealthCheckResponse TS type. Returns
HTTP 200 with status "degraded" when a non-critical dependency is down,
and HTTP 503 only when the service cannot serve traffic at all — Module 1
treats any dependency being down as non-fatal since there are no business
routes depending on them yet.
"""

import time

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.responses import ApiSuccess, success_response
from app.db.health import check_database
from app.db.redis_client import check_redis
from app.schemas.health import DependencyHealth, HealthCheckResponse, HealthDependencies

router = APIRouter(tags=["health"])
_settings = get_settings()
_started_at = time.monotonic()


def _overall_status(statuses: list[str]) -> str:
    if all(s == "ok" for s in statuses):
        return "ok"
    if any(s == "ok" for s in statuses):
        return "degraded"
    return "down"


@router.get("/health", response_model=ApiSuccess[HealthCheckResponse])
async def health_check() -> ApiSuccess[HealthCheckResponse]:
    db_status, db_latency, db_message = await check_database()
    redis_status, redis_latency, redis_message = await check_redis()

    payload = HealthCheckResponse(
        status=_overall_status([db_status, redis_status]),
        service=_settings.service_name,
        version=_settings.service_version,
        uptime_seconds=round(time.monotonic() - _started_at, 2),
        dependencies=HealthDependencies(
            database=DependencyHealth(status=db_status, latency_ms=db_latency, message=db_message),
            redis=DependencyHealth(
                status=redis_status, latency_ms=redis_latency, message=redis_message
            ),
        ),
    )
    return success_response(payload)


@router.get("/health/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    """Pure liveness probe — no dependency checks. Used by container orchestrators."""
    return {"status": "ok"}
