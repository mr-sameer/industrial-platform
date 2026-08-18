"""
CensusCBPAdapter — Module 6D. The industrial-statistics source
selected in docs/product/phase-6c-usa-first-industrial-data-source-strategy-architecture.md
Section 9 — real, live-tested (both in that document's own session and
again this module): `api.census.gov/data/{year}/cbp` with
`get=ESTAB,EMP,PAYANN,NAICS2017_LABEL,NAME&for=state:{fips}&NAICS2017={code}&key={key}`
confirmed to return a real establishment count / employment / payroll
row for one (year, state, NAICS) combination this module (e.g. NAICS
333, Machinery Manufacturing, California: real, non-zero counts).
Every field name below (ESTAB, EMP, PAYANN, PAYQTR1, LFO, NAICS2017)
was independently confirmed against `.../variables.json` this module —
not assumed.

ABSOLUTE RULE (Module 6D Section 25), enforced by construction, not by
convention: this adapter's output never contains a company name, never
an entity identifier — CBP is aggregate/statistical by design (a
disclosure-avoidance rule Census itself enforces; see this file's own
`raw_content`, which has no field that could be mistaken for one). Per
docs/product/.../Section 13 and Module 6D's own instruction, this
source's CollectedItems are never passed through Company entity
resolution — see app.collectors.field_profiles, which deliberately has
no profile registered for `collector_type="census_cbp"`, and
app.services.pilot_service's USA orchestration, which never calls
entity resolution for this collector_type.

Idempotency key (per Module 6D Section 47 — "a Census observation
should conceptually be identifiable by its dimensions"): this
adapter's own `external_identifier` is a deterministic string built
from year+geography+NAICS ("cbp:{year}:state:{fips}:naics:{code}"),
not a value Census itself returns — re-running the identical query
dimensions is recognized as the identical observation by
app.services.acquisition_service's existing idempotency check (source_id
+ external_identifier), with zero schema change.
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

_API_BASE_URL = "https://api.census.gov/data"
_DEFAULT_TIMEOUT_SECONDS = 15.0
# Pilot-size ceiling (Module 6D Section 42: "a small deterministic set
# of geography + NAICS + year observations") — enforced here, matching
# MCADataGovInAdapter's own precedent.
_MAX_QUERIES = 10
_GET_FIELDS = "ESTAB,EMP,PAYANN,PAYQTR1,LFO,NAICS2017,NAICS2017_LABEL,NAME"


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CensusCBPAdapter(SourceAdapter):
    """
    config keys:
      api_key (required)  — a real Census API key.
      year (required)     — a real CBP reference year, e.g. "2023".
      queries (required)  — a list of {"state_fips": "06", "naics": "333"}
                             dicts, at most _MAX_QUERIES entries. Each
                             produces exactly one API call and, if
                             non-empty, exactly one CollectedItem — one
                             (year, geography, NAICS) aggregate
                             observation per query, matching Section
                             47's statistical-identity model.
    """

    adapter_type = "census_cbp"

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config.get("api_key"):
            raise NonRetryableCollectorError("Missing required config key: api_key")
        if not config.get("year"):
            raise NonRetryableCollectorError("Missing required config key: year")
        queries = config.get("queries")
        if not isinstance(queries, list) or not queries:
            raise NonRetryableCollectorError(
                "config key 'queries' must be a non-empty list of "
                "{'state_fips': ..., 'naics': ...} dicts"
            )
        if len(queries) > _MAX_QUERIES:
            raise NonRetryableCollectorError(
                f"config key 'queries' exceeds this pilot's approved ceiling of "
                f"{_MAX_QUERIES} (Module 6D Section 42)"
            )
        for q in queries:
            if not isinstance(q, dict) or not q.get("state_fips") or not q.get("naics"):
                raise NonRetryableCollectorError(
                    "Every entry in 'queries' needs both 'state_fips' and 'naics'"
                )

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        year = config["year"]
        api_key = config["api_key"]
        items: list[CollectedItem] = []
        for q in config["queries"]:
            item = self._collect_one(year, api_key, q["state_fips"], q["naics"])
            if item is not None:
                items.append(item)
        return items

    def _collect_one(
        self, year: str, api_key: str, state_fips: str, naics: str
    ) -> CollectedItem | None:
        url = f"{_API_BASE_URL}/{year}/cbp"
        try:
            response = httpx.get(
                url,
                params={
                    "get": _GET_FIELDS,
                    "for": f"state:{state_fips}",
                    "NAICS2017": naics,
                    "key": api_key,
                },
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out contacting Census CBP: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect to Census CBP: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise RetryableCollectorError(f"Network error contacting Census CBP: {exc}") from exc

        if response.status_code in (401, 403):
            raise NonRetryableCollectorError(
                f"Authentication failed against Census CBP (HTTP {response.status_code}) — "
                "check the configured api_key. Retrying will not help."
            )
        if response.status_code == 429:
            raise RetryableCollectorError("Census CBP rate limit hit (HTTP 429).")
        if response.status_code >= 500:
            raise RetryableCollectorError(f"Census CBP server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            raise NonRetryableCollectorError(
                f"Unexpected Census CBP response for state={state_fips} NAICS={naics}: "
                f"HTTP {response.status_code} — {response.text[:200]}"
            )

        try:
            rows = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NonRetryableCollectorError(
                f"Malformed (non-JSON) response from Census CBP: {exc}"
            ) from exc

        if not isinstance(rows, list) or len(rows) < 1:
            raise NonRetryableCollectorError(
                "Census CBP response has no header row — unexpected response shape."
            )
        if len(rows) < 2:
            # A real, valid outcome (Section 25's disclosure-avoidance
            # rule can suppress a cell entirely) — not an error. Header
            # row present, zero data rows: genuinely nothing to report
            # for this (year, geography, NAICS) combination.
            return None

        header = rows[0]
        data_row = rows[1]
        record = dict(zip(header, data_row, strict=True))
        return self._to_collected_item(year, state_fips, naics, record)

    def _to_collected_item(
        self, year: str, state_fips: str, naics: str, record: dict[str, Any]
    ) -> CollectedItem:
        raw_content: dict[str, Any] = {
            "year": year,
            "state_fips": state_fips,
            "naics2017": record.get("NAICS2017"),
            "naics2017_label": record.get("NAICS2017_LABEL"),
            "geography_name": record.get("NAME"),
            "establishments": record.get("ESTAB"),
            "employees": record.get("EMP"),
            "annual_payroll_thousands": record.get("PAYANN"),
            "q1_payroll_thousands": record.get("PAYQTR1"),
            "legal_form_of_organization": record.get("LFO"),
        }
        external_identifier = f"cbp:{year}:state:{state_fips}:naics:{naics}"
        return CollectedItem(
            raw_content=raw_content,
            content_hash=_content_hash(raw_content),
            external_identifier=external_identifier,
        )

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "U.S. Census Bureau",
            "dataset": "County Business Patterns (CBP)",
            "license_reference": "U.S. government work — public domain",
            "data_shape_note": (
                "Aggregate statistics by (geography, NAICS, year) only — never an "
                "individual company or facility. Never enters Company entity resolution."
            ),
        }


__all__ = ["CensusCBPAdapter"]
