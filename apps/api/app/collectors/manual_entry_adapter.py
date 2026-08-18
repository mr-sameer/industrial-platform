"""
ManualEntryAdapter — Module 6D. Makes manual data entry a first-class
`source_type = MANUAL` citizen of the existing acquisition/provenance/
entity-resolution trust pipeline, per this module's own requirement
("Manual data must be treated as a legitimate source type... must not
bypass validation, provenance, data quality, entity resolution,
conflict detection, verification state").

WHY AN ADAPTER, NOT A NEW ENDPOINT/TABLE: an authorized user submitting
one company/factory/product record by hand is, structurally, identical
to a collector run that "discovers" exactly one item — the config *is*
the one record, and there is nothing left to fetch externally. Modeling
it as a SourceAdapter means manual entry gets every real mechanism
Module 5B/5D already built — idempotency (app.services.acquisition_service),
job/event auditing (AcquisitionJob/AcquisitionJobEvent), redaction,
entity resolution (via app.collectors.field_profiles's "manual_entry"
profile), and human review/promotion (app.services.company_promotion_service,
already generalized in Module 6D) — for zero new persistence, zero new
API route, and zero schema change. `POST /api/v1/acquisition/jobs`
(Role.ADMIN-gated, Module 5B, unmodified) with
`collector_type="manual_entry"` IS the manual-entry submission endpoint.

Restricted to Role.ADMIN by the existing route (app/api/v1/acquisition.py)
— per this module's own instruction not to expose an unrestricted
public creation endpoint and not to invent a new security model where
an existing one (Module 2's platform Role) already applies. See this
module's completion report for why a narrower, per-company role would
be a real future improvement, not built here.

`entered_by`/`evidence_url`/`notes` describe the *submission*, not a
fact about the company — they're preserved on the raw observation
itself (visible via `GET /acquisition/observations/{id}`, Module 5C)
for audit purposes, but deliberately excluded from
app.collectors.field_profiles's manual_entry direct/extra field lists,
so they never become a company-fact ProvenanceRecord.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.collectors.base import CollectedItem, NonRetryableCollectorError, SourceAdapter

_REQUIRED_FIELDS = ("company_name", "entered_by")


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ManualEntryAdapter(SourceAdapter):
    """
    config keys (== the submitted record itself — this is the one
    adapter where `requested_scope` IS the data, not query parameters):
      company_name (required) — the entity's name, as the submitter
                                 states it.
      entered_by (required)   — the submitting user's id (string form)
                                 — a real, attributable actor, never
                                 anonymous, matching Module 6D Section 11.
      industry, state, city, website, country, description (optional)
      evidence_url (optional) — a link the submitter offers as support.
                                 Never treated as verification by itself
                                 (Module 6D Section 58) — only a future,
                                 separate provenance_service.verify_provenance_record
                                 call can do that.
      notes (optional)
    """

    adapter_type = "manual_entry"

    def validate_config(self, config: dict[str, Any]) -> None:
        missing = [f for f in _REQUIRED_FIELDS if not config.get(f)]
        if missing:
            raise NonRetryableCollectorError(
                f"Missing required config key(s): {', '.join(missing)}"
            )

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        # No external call — the config itself is the one record a
        # human submitted "collecting" it. Never marks anything
        # verified/promoted here — this only produces a RawObservation;
        # promotion to a canonical Company stays a distinct, later,
        # human-gated action (app.services.company_promotion_service),
        # exactly as for any other source.
        raw_content = dict(config)
        return [
            CollectedItem(
                raw_content=raw_content,
                content_hash=_content_hash(raw_content),
                # Evidence URL, when given, is the closest thing to a
                # stable external reference a manual submission has;
                # falls back to None (content_hash-only idempotency)
                # otherwise — a second, distinct submission with the
                # same content is then correctly treated as identical,
                # matching every other adapter's own strategy.
                external_identifier=config.get("evidence_url"),
            )
        ]

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "ForgeX platform users (authorized)",
            "dataset": "Manually entered industrial data",
            "data_shape_note": (
                "Never auto-verified — source_type=MANUAL flows through the identical "
                "validation/provenance/entity-resolution/review pipeline as any API source."
            ),
        }


__all__ = ["ManualEntryAdapter"]
