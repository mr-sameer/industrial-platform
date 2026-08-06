"""
Canonical API envelope helpers — the Python-side mirror of
packages/shared-types/src/api-response.ts. See
docs/standards/api-response-standard.md for the full contract.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiMeta(BaseModel):
    request_id: str
    timestamp: str


def make_meta(request_id: str | None = None) -> ApiMeta:
    return ApiMeta(
        request_id=request_id or str(uuid.uuid4()),
        timestamp=datetime.now(UTC).isoformat(),
    )


class ApiSuccess(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: ApiMeta


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    details: Any | None = None


class ApiError(BaseModel):
    success: bool = False
    error: ApiErrorDetail
    meta: ApiMeta


def success_response(data: T, request_id: str | None = None) -> ApiSuccess[T]:
    return ApiSuccess(data=data, meta=make_meta(request_id))


def error_response(
    code: str, message: str, field: str | None = None, details: Any | None = None
) -> ApiError:
    return ApiError(
        error=ApiErrorDetail(code=code, message=message, field=field, details=details),
        meta=make_meta(),
    )
