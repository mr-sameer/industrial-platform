"""
Centralized, typed application settings.

All configuration flows through this module — nothing else in the codebase
should call os.environ / os.getenv directly. That keeps every setting
discoverable in one place and lets pydantic validate types and required
values at startup instead of failing deep inside request handling.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_local_upload_path() -> str:
    """
    Default for `upload_storage_path` when nothing else specifies it —
    i.e. genuinely bare `uvicorn app.main:app --reload`, no `.env`
    override. Deliberately NOT a Docker path ("/app/uploads" only
    exists inside the container filesystem — see
    docs/adr/0030-upload-storage-path-configuration-bug.md for the
    incident this fixes). Computed relative to this file's own location
    (apps/api/app/core/config.py -> apps/api/uploads), not the process's
    current working directory, so it resolves to the same real,
    writable place regardless of which directory `uvicorn` was invoked
    from. Docker overrides this via an explicit UPLOAD_STORAGE_PATH env
    var (docker-compose.yml) and always has, unaffected by this change.
    """
    return str(Path(__file__).resolve().parent.parent.parent / "uploads")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- General ----
    environment: str = Field(default="development")
    log_level: str = Field(default="info")
    service_name: str = Field(default="industrial-platform-api")
    service_version: str = Field(default="0.1.0")

    # ---- API ----
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_cors_origins: str = Field(default="http://localhost:3000")

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+asyncpg://platform_user:change_me_locally@localhost:5432/industrial_platform"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://platform_user:change_me_locally@localhost:5432/industrial_platform"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=5)

    # ---- Redis ----
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ---- Auth (Module 2) ----
    # NOTE: the default below is fine for local dev only. Every non-local
    # environment MUST set JWT_SECRET_KEY explicitly — see .env.example
    # and docs/adr/0010-jwt-authentication-strategy.md.
    jwt_secret_key: str = Field(default="dev-only-insecure-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=15)
    jwt_refresh_token_expire_days: int = Field(default=7)

    # ---- Auth hardening (Module 2.5) ----
    # Used to build links in emails (verification, password reset) — the
    # API has no server-rendered pages of its own, so these always point
    # at the web app.
    web_app_base_url: str = Field(default="http://localhost:3000")

    # ---- File storage (Module 3B) ----
    # See app.core.storage — LocalStorageBackend today; both of these
    # exist so a future S3Backend only needs new env vars, not new code
    # paths, to take over (bucket name / endpoint would replace
    # storage_path / public_base_url).
    upload_storage_path: str = Field(default_factory=_default_local_upload_path)
    upload_public_base_url: str = Field(default="http://localhost:8000/uploads")
    upload_max_logo_size_bytes: int = Field(default=5 * 1024 * 1024)  # 5 MB
    upload_max_cover_size_bytes: int = Field(default=10 * 1024 * 1024)  # 10 MB
    upload_max_document_size_bytes: int = Field(default=15 * 1024 * 1024)  # 15 MB

    # Rate limiting (Redis-backed, see app.core.rate_limit). Each pair is
    # (max attempts, window in seconds) unless noted otherwise.
    rate_limit_login_per_ip: int = Field(default=10)
    rate_limit_login_per_ip_window_seconds: int = Field(default=60)
    rate_limit_login_per_account: int = Field(default=5)
    rate_limit_login_per_account_window_seconds: int = Field(default=300)
    rate_limit_register_per_ip: int = Field(default=5)
    rate_limit_register_per_ip_window_seconds: int = Field(default=3600)
    rate_limit_forgot_password_per_ip: int = Field(default=5)
    rate_limit_forgot_password_per_ip_window_seconds: int = Field(default=3600)
    rate_limit_refresh_per_ip: int = Field(default=30)
    rate_limit_refresh_per_ip_window_seconds: int = Field(default=60)
    rate_limit_verify_email_per_ip: int = Field(default=10)
    rate_limit_verify_email_per_ip_window_seconds: int = Field(default=3600)

    # ---- USA industrial data sources (Module 6D) ----
    # Both already existed in .env before this field was added (real
    # local credentials) — this just exposes them through the one
    # sanctioned config path (see this module's own docstring: nothing
    # else may call os.getenv directly). SEC EDGAR's public API needs
    # no key, only a self-identifying User-Agent — see
    # app.collectors.sec_edgar_adapter.
    census_api_key: str | None = Field(default=None)
    usitc_dataweb_api_token: str | None = Field(default=None)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _guard_default_jwt_secret_in_production(self) -> "Settings":
        if self.is_production and self.jwt_secret_key == "dev-only-insecure-secret-change-me":
            raise ValueError(
                "JWT_SECRET_KEY must be set to a real secret when ENVIRONMENT=production"
            )
        return self

    @model_validator(mode="after")
    def _guard_wildcard_cors_in_production(self) -> "Settings":
        """
        Closes architecture-review weakness #12: nothing previously
        stopped API_CORS_ORIGINS=* (or a comma-separated list containing
        "*") from being deployed to production, which combined with
        allow_credentials=True in main.py's CORSMiddleware would let any
        origin make credentialed requests. Fail fast at startup instead.
        """
        if self.is_production and "*" in self.cors_origins_list:
            raise ValueError(
                "API_CORS_ORIGINS must not contain '*' when ENVIRONMENT=production "
                "(combined with allow_credentials=True, a wildcard origin would let "
                "any site make credentialed requests)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — safe to call repeatedly (e.g. as a FastAPI dependency)."""
    return Settings()
