from pydantic import BaseModel

Status = str  # "ok" | "degraded" | "down" — kept as str to match the TS union at the JSON boundary


class DependencyHealth(BaseModel):
    status: Status
    latency_ms: float | None = None
    message: str | None = None


class HealthDependencies(BaseModel):
    database: DependencyHealth
    redis: DependencyHealth


class HealthCheckResponse(BaseModel):
    status: Status
    service: str
    version: str
    uptime_seconds: float
    dependencies: HealthDependencies
