"""Source adapter / collector framework — Module 5B."""

from app.collectors.base import (
    CollectedItem,
    NonRetryableCollectorError,
    RetryableCollectorError,
    SourceAdapter,
)

__all__ = [
    "CollectedItem",
    "NonRetryableCollectorError",
    "RetryableCollectorError",
    "SourceAdapter",
]
