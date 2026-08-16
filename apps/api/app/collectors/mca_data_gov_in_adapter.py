"""
MCADataGovInAdapter — Module 5C. A real SourceAdapter implementation
for the pilot source selected and approved in
docs/product/phase-5c-india-company-data-source-architecture.md
Section 3: MCA Company Master Data, accessed via data.gov.in's
structured API (confirmed real, key-based, resource_id-addressed —
Section 2 of that document).

FIELD NAMES used below (CIN, Company Name, Company Status, Company
Class, Company Category, Authorized Capital, Paid-up Capital, Date of
Registration, Registered State, Registrar of Companies, Principal
Business Activity, Registered Office Address, Sub Category) are the
CONFIRMED, real field list from the dataset's own official catalog
description (data.gov.in/catalog/company-master-data), verified via
web research while writing the Phase 5C architecture document — not
invented. The exact JSON key casing data.gov.in's API returns these
under was NOT independently confirmed by a live API call (see this
module's own completion report for why: this sandbox's network egress
cannot reach data.gov.in — confirmed empirically, HTTP 403 from the
egress proxy on every subdomain tried, plus a separate robots.txt
block via web_fetch). `_extract_field` below defends against this
uncertainty by trying multiple plausible key-casing variants rather
than assuming one — but the exact casing should be confirmed against
a real response the first time this adapter actually runs, and this
is flagged explicitly, not silently assumed correct.

This adapter follows the SourceAdapter contract exactly as Module 5B
defined it (app/collectors/base.py) — nothing here is hard-coded into
acquisition_service.py; it plugs into the same
app.collectors.registry mechanism as MockSourceAdapter.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from app.collectors.base import (
    CollectedItem,
    NonRetryableCollectorError,
    RetryableCollectorError,
    SourceAdapter,
)

# The real, confirmed data.gov.in API base — resource-scoped REST
# endpoint, key-based auth via the `api-key` query parameter, `format`
# and `limit`/`offset` for pagination. Confirmed via web research
# (multiple independent client libraries and the platform's own help
# documentation agree on this shape) — not independently confirmed via
# a live call from this environment (see this module's docstring).
_API_BASE_URL = "https://api.data.gov.in/resource"
_DEFAULT_TIMEOUT_SECONDS = 15.0

# Real, confirmed field names from the dataset's own catalog
# description — several plausible JSON-key casings are tried for each,
# since the exact casing wasn't independently confirmed (see module
# docstring).
_FIELD_KEY_VARIANTS: dict[str, list[str]] = {
    "cin": ["CIN", "cin", "Corporate_identification_number", "corporate_identification_number"],
    "company_name": ["Company Name", "company_name", "CompanyName", "COMPANY_NAME"],
    "company_status": ["Company Status", "company_status", "CompanyStatus"],
    "company_class": ["Company Class", "company_class"],
    "company_category": ["Company Category", "company_category"],
    "sub_category": ["Company SubCategory", "sub_category", "Sub Category"],
    "authorized_capital": ["Authorized Capital", "authorized_capital", "AuthorizedCapital"],
    "paid_up_capital": ["Paid up Capital", "paid_up_capital", "PaidUpCapital"],
    "date_of_registration": ["Date of Registration", "date_of_registration", "DateOfRegistration"],
    "registered_state": ["Registered State", "registered_state", "RegisteredState"],
    "registrar_of_companies": ["Registrar of Companies", "registrar_of_companies", "ROC"],
    "principal_business_activity": [
        "Principal Business Activity",
        "principal_business_activity",
        "PrincipalBusinessActivity",
    ],
    "registered_office_address": [
        "Registered Office Address",
        "registered_office_address",
        "RegisteredOfficeAddress",
    ],
}


def _extract_field(record: dict[str, Any], field: str) -> str | None:
    for key in _FIELD_KEY_VARIANTS[field]:
        if key in record and record[key] not in (None, ""):
            value = record[key]
            return str(value).strip()
    return None


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MCADataGovInAdapter(SourceAdapter):
    """
    config keys:
      api_key (required)         — the data.gov.in account API key
      resource_id (required)     — the specific dataset's resource ID
                                    on data.gov.in (per-ROC datasets
                                    exist; a real operator selects one
                                    or iterates — this pilot's config
                                    scopes to exactly one per job, per
                                    Section 9's small pilot size)
      limit (optional, default 50, capped at 50 for this pilot per the
                                    approved architecture's pilot-size
                                    recommendation — see Section 9 of
                                    the architecture doc)
      offset (optional, default 0)
    """

    adapter_type = "mca_data_gov_in"

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config.get("api_key"):
            raise NonRetryableCollectorError("Missing required config key: api_key")
        if not config.get("resource_id"):
            raise NonRetryableCollectorError("Missing required config key: resource_id")
        limit = config.get("limit", 50)
        if not isinstance(limit, int) or limit <= 0:
            raise NonRetryableCollectorError("config key 'limit' must be a positive integer")
        if limit > 50:
            # Pilot-size ceiling, enforced here rather than left to
            # convention — per the approved architecture's Section 9
            # recommendation (25-50 companies), not a technical API
            # limit.
            raise NonRetryableCollectorError(
                "config key 'limit' exceeds this pilot's approved ceiling of 50 "
                "(see docs/product/phase-5c-india-company-data-source-architecture.md Section 9)"
            )
        offset = config.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            raise NonRetryableCollectorError("config key 'offset' must be a non-negative integer")

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        api_key = config["api_key"]
        resource_id = config["resource_id"]
        limit = config.get("limit", 50)
        offset = config.get("offset", 0)
        url = f"{_API_BASE_URL}/{resource_id}"

        try:
            response = httpx.get(
                url,
                params={"api-key": api_key, "format": "json", "limit": limit, "offset": offset},
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out contacting data.gov.in: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect to data.gov.in: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001 — any other transport-level failure is treated as retryable, not silently swallowed
            raise RetryableCollectorError(f"Network error contacting data.gov.in: {exc}") from exc

        if response.status_code in (401, 403):
            raise NonRetryableCollectorError(
                f"Authentication failed against data.gov.in (HTTP {response.status_code}) — "
                "check the configured api_key. Retrying will not help."
            )
        if response.status_code == 429:
            raise RetryableCollectorError("data.gov.in rate limit hit (HTTP 429).")
        if response.status_code >= 500:
            raise RetryableCollectorError(
                f"data.gov.in server error (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            raise NonRetryableCollectorError(
                f"Unexpected data.gov.in response: HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NonRetryableCollectorError(
                f"Malformed (non-JSON) response from data.gov.in: {exc}"
            ) from exc

        records = body.get("records")
        if records is None:
            raise NonRetryableCollectorError(
                "data.gov.in response has no 'records' field — unexpected response shape."
            )

        return [self._to_collected_item(record) for record in records]

    def _to_collected_item(self, record: dict[str, Any]) -> CollectedItem:
        cin = _extract_field(record, "cin")
        raw_content: dict[str, Any] = {
            "cin": cin,
            "company_name": _extract_field(record, "company_name"),
            "company_status": _extract_field(record, "company_status"),
            "company_class": _extract_field(record, "company_class"),
            "company_category": _extract_field(record, "company_category"),
            "sub_category": _extract_field(record, "sub_category"),
            "authorized_capital": _extract_field(record, "authorized_capital"),
            "paid_up_capital": _extract_field(record, "paid_up_capital"),
            "date_of_registration": _extract_field(record, "date_of_registration"),
            "registered_state": _extract_field(record, "registered_state"),
            "registrar_of_companies": _extract_field(record, "registrar_of_companies"),
            "principal_business_activity": _extract_field(record, "principal_business_activity"),
            "registered_office_address": _extract_field(record, "registered_office_address"),
        }
        return CollectedItem(
            raw_content=raw_content,
            content_hash=_content_hash(raw_content),
            external_identifier=cin,
        )

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "Ministry of Corporate Affairs, Government of India",
            "publisher": "Open Government Data (OGD) Platform India (data.gov.in)",
            "dataset": "Company Master Data",
            "license_reference": "National Data Sharing and Accessibility Policy (NDSAP), 2012",
        }


__all__ = ["MCADataGovInAdapter"]
