"""
MockSourceAdapter — Module 5B. The one and only collector this phase
connects to anything — deliberately not a real external website or
API (this module's explicit scope boundary). Exists to prove the
entire pipeline (source -> adapter -> job -> observation -> provenance)
end to end without any external dependency, and to let tests
deterministically exercise both the retry path and the non-retry
failure path via config, rather than depending on real network
flakiness to exercise those code paths at all.
"""

import hashlib
import json
from typing import Any

from app.collectors.base import (
    CollectedItem,
    NonRetryableCollectorError,
    RetryableCollectorError,
    SourceAdapter,
)

# A small, fixed fixture — deterministic across every run, exactly what
# "known observations" means for this adapter. Each item carries a
# stable external_identifier, matching what a real adapter would
# provide (a URL, a registry record ID) for the primary idempotency
# key acquisition_service uses.
_FIXTURE_ITEMS: list[dict[str, Any]] = [
    {
        "external_identifier": "mock://fixture/1",
        "raw_content": {"name": "Fixture Industrial Co", "country": "IN"},
    },
    {
        "external_identifier": "mock://fixture/2",
        "raw_content": {"name": "Fixture Motors Ltd", "country": "IN"},
    },
    {
        "external_identifier": "mock://fixture/3",
        "raw_content": {"name": "Fixture Valves Pvt Ltd", "country": "IN"},
    },
]


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MockSourceAdapter(SourceAdapter):
    adapter_type = "mock"

    def validate_config(self, config: dict[str, Any]) -> None:
        simulate_failure = config.get("simulate_failure")
        if simulate_failure is not None and simulate_failure not in (
            "timeout",
            "rate_limit",
            "invalid_credentials",
            "malformed_config",
            "partial",
            "all_invalid",
        ):
            raise NonRetryableCollectorError(
                f"Unknown simulate_failure value: {simulate_failure!r}. "
                "Expected one of: timeout, rate_limit, invalid_credentials, malformed_config, partial, all_invalid."
            )
        if simulate_failure == "malformed_config":
            # Deliberately raised here, not in collect() — an invalid
            # configuration should fail validation before any
            # collection attempt, per SourceAdapter.validate_config's
            # own contract.
            raise NonRetryableCollectorError("Simulated malformed configuration.")

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        simulate_failure = config.get("simulate_failure")
        if simulate_failure in ("timeout", "rate_limit"):
            raise RetryableCollectorError(
                f"Simulated {simulate_failure} — this is expected to be retried."
            )
        if simulate_failure == "invalid_credentials":
            raise NonRetryableCollectorError(
                "Simulated authentication failure — invalid credentials."
            )

        if simulate_failure == "partial":
            # One item deliberately has empty raw_content — genuinely
            # invalid (RawObservationCreate requires min_length=1), so
            # it fails real validation downstream in
            # provenance_service.create_raw_observation while the
            # other two items succeed normally. Not a fabricated
            # failure mode — an authentic one, using the same
            # validation every other observation goes through.
            return [
                CollectedItem(
                    raw_content=_FIXTURE_ITEMS[0]["raw_content"],
                    content_hash=_content_hash(_FIXTURE_ITEMS[0]["raw_content"]),
                    external_identifier=_FIXTURE_ITEMS[0]["external_identifier"],
                ),
                CollectedItem(
                    raw_content={},
                    content_hash=_content_hash({}),
                    external_identifier="mock://fixture/invalid",
                ),
                CollectedItem(
                    raw_content=_FIXTURE_ITEMS[2]["raw_content"],
                    content_hash=_content_hash(_FIXTURE_ITEMS[2]["raw_content"]),
                    external_identifier=_FIXTURE_ITEMS[2]["external_identifier"],
                ),
            ]

        if simulate_failure == "all_invalid":
            # Every item has empty raw_content — the genuine
            # all-items-failed boundary, real end to end, not simulated
            # via duplicated inline logic in a test.
            return [
                CollectedItem(
                    raw_content={},
                    content_hash=_content_hash({}),
                    external_identifier=f"mock://invalid/{i}",
                )
                for i in range(3)
            ]

        return [
            CollectedItem(
                raw_content=item["raw_content"],
                content_hash=_content_hash(item["raw_content"]),
                external_identifier=item["external_identifier"],
            )
            for item in _FIXTURE_ITEMS
        ]

    def source_metadata(self) -> dict[str, Any]:
        return {"adapter_type": self.adapter_type, "fixture_item_count": len(_FIXTURE_ITEMS)}
