"""
USITCDataWebAdapter — Module 6D. The trade-intelligence source
selected in docs/product/phase-6c-usa-first-industrial-data-source-strategy-architecture.md
Section 11. Every endpoint/shape below was verified live this module
(not assumed from memory, per this ticket's own explicit instruction)
against the real, official API User Guide
(https://www.usitc.gov/sites/default/files/applications/dataweb/api/dataweb_query_api.html)
plus real, live calls made while building this adapter:
  - baseUrl = https://datawebws.usitc.gov/dataweb (confirmed real, per
    the guide's own example code).
  - GET  {baseUrl}/api/v2/query/getGlobalVars — unauthenticated, real,
    live-confirmed 200 this module (returned real current-period
    metadata: currentYear/currentFullReportingYear).
  - GET  {baseUrl}/api/v2/savedQuery/getAllSavedQueries — Authorization:
    Bearer {token}, real, live-confirmed 200 this module with the
    configured USITC_DATAWEB_API_TOKEN (a genuinely valid, working
    token — confirmed by a successful authenticated response, not by
    assumption).
  - POST {baseUrl}/api/v2/report2/runReport — same Bearer header; the
    JSON body is the ENTIRE saved-query object returned by
    getAllSavedQueries for the matched query (confirmed directly from
    the official guide's own example code: `requests.post(...,
    json=CrabExample_res, ...)` where CrabExample_res IS the matched
    saved-query dict, not a separately-constructed body). This adapter
    does exactly that — never hand-builds a query definition, since
    the one documented, confirmed-correct way to obtain one is the
    account's own saved query, built once via the MFA-gated (Login.gov)
    DataWeb web UI.

REAL, CONFIRMED CONSTRAINT (not hypothetical — checked live while
building this adapter): the account behind the configured token
currently has ZERO saved queries. USITC's own documented access
pattern requires at least one to exist — built through the web UI,
which this adapter cannot do headlessly, and Module 6D's own Section 26
explicitly scoped out any attempt to reverse-engineer a runReport
request body from first principles. Until a real saved query exists,
`validate_config` still passes (config is structurally valid) but
`collect()` honestly fails NonRetryable with an actionable message —
never a fabricated result. See this module's own completion report for
the exact BLOCKED status this produces in a real pilot run.

Response shape (confirmed via the same official guide): result rows
live at `dto.tables[measure_index].row_groups[0].rowsNew`, each row's
values under `rowEntries[*].value`; column labels come from
`dto.tables[measure_index].column_groups`, recursively (a group either
has nested `columns` or a leaf `label`) — mirrored here by
`_flatten_columns`, a direct port of the guide's own `getColumns()`.

Trade observations never enter Company entity resolution — see
app.collectors.field_profiles (no profile registered for
`collector_type="usitc_dataweb"`) and Module 6D Section 28/36.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import httpx

from app.collectors.base import (
    CollectedItem,
    NonRetryableCollectorError,
    RetryableCollectorError,
    SourceAdapter,
)

_BASE_URL = "https://datawebws.usitc.gov/dataweb"
_DEFAULT_TIMEOUT_SECONDS = 20.0
_MAX_MEASURE_INDEXES = 5  # a small, bounded cap — never "every measure the account has ever saved"


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _flatten_columns(column_groups: list[Any], columns: list[str] | None = None) -> list[str]:
    """Direct port of the official API User Guide's own getColumns()
    helper — the column-label extraction shape is Section 2/3 of that
    guide's example code, reproduced exactly, not reinvented."""
    if columns is None:
        columns = []
    for group in column_groups:
        if isinstance(group, dict) and "columns" in group:
            _flatten_columns(group["columns"], columns)
        elif isinstance(group, dict) and "label" in group:
            columns.append(group["label"])
        elif isinstance(group, list):
            _flatten_columns(group, columns)
    return columns


def _flatten_rows(row_groups: list[Any]) -> list[list[Any]]:
    """Direct port of the guide's own getData() helper."""
    data: list[list[Any]] = []
    for row in row_groups:
        entries = row.get("rowEntries", [])
        data.append([entry.get("value") for entry in entries])
    return data


class USITCDataWebAdapter(SourceAdapter):
    """
    config keys:
      token (required)            — a real USITC DataWeb API token
                                     (Authorization: Bearer). Expires
                                     every 6 months, does not auto-renew
                                     (real, documented USITC behavior).
      saved_query_name (required) — the exact `savedQueryName` of a
                                     query already saved in this
                                     account's DataWeb web UI. This
                                     adapter never constructs a runReport
                                     body itself — see this file's own
                                     docstring for why.
    """

    adapter_type = "usitc_dataweb"

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config.get("token"):
            raise NonRetryableCollectorError("Missing required config key: token")
        if not config.get("saved_query_name"):
            raise NonRetryableCollectorError("Missing required config key: saved_query_name")

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['token']}",
        }
        saved_query = self._find_saved_query(config["saved_query_name"], headers)
        report = self._run_report(saved_query, headers)
        return self._to_collected_items(config["saved_query_name"], report)

    def _find_saved_query(self, saved_query_name: str, headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{_BASE_URL}/api/v2/savedQuery/getAllSavedQueries",
                headers=headers,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out contacting USITC DataWeb: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect to USITC DataWeb: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise RetryableCollectorError(f"Network error contacting USITC DataWeb: {exc}") from exc

        self._raise_for_status(response, "USITC DataWeb getAllSavedQueries")

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NonRetryableCollectorError(
                f"Malformed (non-JSON) response from getAllSavedQueries: {exc}"
            ) from exc

        all_queries = body.get("list", [])
        match = next((q for q in all_queries if q.get("savedQueryName") == saved_query_name), None)
        if match is None:
            raise NonRetryableCollectorError(
                f"No saved query named {saved_query_name!r} exists in this DataWeb account "
                f"({len(all_queries)} saved quer{'y' if len(all_queries) == 1 else 'ies'} found). "
                "USITC's documented API workflow requires building at least one saved query "
                "through the DataWeb web UI (https://dataweb.usitc.gov) first — this adapter "
                "cannot create one headlessly. See this adapter's own module docstring."
            )
        # httpx's .json() is typed Any (genuinely untyped JSON) — cast,
        # not ignore, since the shape is real and confirmed (a dict from
        # getAllSavedQueries's own "list" array) — not merely suppressed.
        return cast(dict[str, Any], match)

    def _run_report(self, saved_query: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{_BASE_URL}/api/v2/report2/runReport",
                headers=headers,
                json=saved_query,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out running USITC report: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect to USITC DataWeb: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise RetryableCollectorError(f"Network error running USITC report: {exc}") from exc

        self._raise_for_status(response, "USITC DataWeb runReport")

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NonRetryableCollectorError(
                f"Malformed (non-JSON) response from runReport: {exc}"
            ) from exc
        return cast(dict[str, Any], body)

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code in (401, 403):
            raise NonRetryableCollectorError(
                f"{context}: authentication failed (HTTP {response.status_code}) — check the "
                "configured token (USITC tokens expire every 6 months and do not auto-renew). "
                "Retrying will not help."
            )
        if response.status_code == 429:
            raise RetryableCollectorError(f"{context}: rate limit hit (HTTP 429).")
        if response.status_code >= 500:
            raise RetryableCollectorError(f"{context}: server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            raise NonRetryableCollectorError(
                f"{context}: unexpected HTTP {response.status_code} — {response.text[:200]}"
            )

    def _to_collected_items(
        self, saved_query_name: str, report: dict[str, Any]
    ) -> list[CollectedItem]:
        tables = (report.get("dto") or {}).get("tables") or []
        if not tables:
            raise NonRetryableCollectorError(
                "USITC runReport response has no 'dto.tables' — unexpected response shape."
            )

        items: list[CollectedItem] = []
        for measure_index, table in enumerate(tables[:_MAX_MEASURE_INDEXES]):
            columns = _flatten_columns(table.get("column_groups", []))
            row_groups = table.get("row_groups") or []
            rows = _flatten_rows(row_groups[0].get("rowsNew", [])) if row_groups else []
            for row_index, row_values in enumerate(rows):
                record = dict(zip(columns, row_values, strict=False))
                raw_content: dict[str, Any] = {
                    "saved_query_name": saved_query_name,
                    "measure_index": measure_index,
                    "row_index": row_index,
                    **{f"col:{k}": v for k, v in record.items()},
                }
                external_identifier = (
                    f"usitc:{saved_query_name}:measure:{measure_index}:row:{row_index}"
                )
                items.append(
                    CollectedItem(
                        raw_content=raw_content,
                        content_hash=_content_hash(raw_content),
                        external_identifier=external_identifier,
                    )
                )
        return items

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "U.S. International Trade Commission",
            "dataset": "DataWeb — U.S. trade and tariff data",
            "license_reference": "U.S. government work — public domain",
            "data_shape_note": (
                "Trade-flow observations (commodity x country x period) only — never "
                "company or facility identity. Never enters Company entity resolution."
            ),
        }


__all__ = ["USITCDataWebAdapter"]
