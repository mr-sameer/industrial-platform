"""
SECEdgarAdapter — Module 6D. The first real USA company-level source,
selected in docs/product/phase-6c-usa-first-industrial-data-source-strategy-architecture.md
Section 10 ("public-company enrichment/corroboration") and Module 6D's
own instruction ("SEC EDGAR is the first company-level source").

Two real, official, key-free endpoints, both confirmed live and
reachable this module (not assumed from memory):
  - Discovery: https://www.sec.gov/cgi-bin/browse-edgar (atom output) —
    lists companies by SIC code. Real, confirmed live response this
    module. NOTE: its <company-info name="..."> and <entry title="...">
    attributes are a long-standing, confirmed-live SEC EDGAR quirk —
    they render as "ARRAY(0x...)" (a PHP internal representation
    leaking through), not the real company name — so this adapter uses
    this endpoint for CIK discovery ONLY, never for the name, exactly
    matching this ticket's own instruction not to invent/guess a field
    value. The real name comes from the per-company detail fetch below.
  - Detail: https://data.sec.gov/submissions/CIK{10-digit}.json — the
    real per-company profile. Confirmed live this module (fetched CIK
    0000320193 / Apple Inc. and verified every field name used below
    appears exactly as read: cik, entityType, sic, sicDescription,
    name, tickers, exchanges, ein, category, fiscalYearEnd,
    stateOfIncorporation, addresses.business.{street1,city,stateOrCountry,zipCode},
    phone, formerNames).

SEC requires no API key for either endpoint, but its own published
policy requires every request to declare a real, identifying
User-Agent (a company/individual name + contact) — requests without
one are documented to receive 403. That contact is supplied by the
operator via config (`user_agent`), exactly like MCADataGovInAdapter's
api_key — never hardcoded here, since a real contact identity is
config, not adapter code.

Deterministic, explainable selection (per Module 6D Section 23): a
fixed SIC (Standard Industrial Classification) code selects an
industrial/manufacturing population — e.g. 3559 "Special Industry
Machinery, NEC" — and the first `limit` distinct CIKs the discovery
endpoint returns (its own real, live ordering, not randomized) are
selected. No company list is invented; a documented, reproducible
method, matching this ticket's own instruction ("Do not fabricate a
company list").
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

import httpx

from app.collectors.base import (
    CollectedItem,
    NonRetryableCollectorError,
    RetryableCollectorError,
    SourceAdapter,
)

_DISCOVERY_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_DEFAULT_TIMEOUT_SECONDS = 15.0
# Pilot-size ceiling (Module 6D Section 42: "SEC: 10-25 real companies")
# — enforced here, not left to convention, matching
# MCADataGovInAdapter's own precedent for its pilot-size ceiling.
_MAX_LIMIT = 25
# A courteous minimum gap between the N per-company detail requests —
# SEC's documented limit is far higher (10 req/s); this is deliberately
# more conservative for a "controlled pilot, not aggressive concurrency"
# (Module 6D Section 50), not a limit SEC itself imposed.
_REQUEST_GAP_SECONDS = 0.2

_CIK_TAG_PATTERN = re.compile(r"<cik>(\d+)</cik>")


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


class SECEdgarAdapter(SourceAdapter):
    """
    config keys:
      user_agent (required)   — a real, identifying contact string, per
                                 SEC's own request-identification policy
                                 (e.g. "ForgeX Pilot contact@example.com").
                                 Never hardcoded in this file.
      sic_code (required)     — a real SEC Standard Industrial
                                 Classification code selecting the
                                 industrial/manufacturing population to
                                 pull from (e.g. "3559").
      limit (optional, default 15, capped at 25 for this pilot per
                                 Module 6D Section 42)
    """

    adapter_type = "sec_edgar"

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config.get("user_agent"):
            raise NonRetryableCollectorError(
                "Missing required config key: user_agent (SEC EDGAR requires a real, "
                "identifying User-Agent on every request — see this adapter's docstring)"
            )
        if not config.get("sic_code"):
            raise NonRetryableCollectorError("Missing required config key: sic_code")
        limit = config.get("limit", 15)
        if not isinstance(limit, int) or limit <= 0:
            raise NonRetryableCollectorError("config key 'limit' must be a positive integer")
        if limit > _MAX_LIMIT:
            raise NonRetryableCollectorError(
                f"config key 'limit' exceeds this pilot's approved ceiling of {_MAX_LIMIT} "
                "(Module 6D Section 42)"
            )

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        headers = {"User-Agent": config["user_agent"]}
        ciks = self._discover_ciks(config["sic_code"], config.get("limit", 15), headers)

        items: list[CollectedItem] = []
        failures: list[str] = []
        for i, cik in enumerate(ciks):
            if i > 0:
                time.sleep(_REQUEST_GAP_SECONDS)
            try:
                items.append(self._fetch_company(cik, headers))
            except (RetryableCollectorError, NonRetryableCollectorError) as exc:
                # One bad company must not abort the whole discovery
                # batch (SourceAdapter's own contract: a genuinely empty
                # *result* must stay distinguishable from a *failed*
                # collection — enforced below, not by silently returning
                # partial data with no signal at all).
                failures.append(f"CIK {cik}: {exc}")

        if not items and failures:
            raise RetryableCollectorError(
                f"All {len(failures)} SEC EDGAR detail fetch(es) failed: {'; '.join(failures)}"
            )
        return items

    def _discover_ciks(self, sic_code: str, limit: int, headers: dict[str, str]) -> list[int]:
        try:
            response = httpx.get(
                _DISCOVERY_URL,
                params={
                    "action": "getcompany",
                    "SIC": sic_code,
                    "type": "10-K",
                    "dateb": "",
                    "owner": "include",
                    "count": str(limit),
                    "output": "atom",
                },
                headers=headers,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out contacting SEC EDGAR: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect to SEC EDGAR: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001 — any other transport failure is retryable, not silently swallowed
            raise RetryableCollectorError(f"Network error contacting SEC EDGAR: {exc}") from exc

        self._raise_for_status(response, "SEC EDGAR discovery")

        ciks = [int(m) for m in _CIK_TAG_PATTERN.findall(response.text)]
        # Preserve real response order, dedupe, cap at `limit` — the
        # discovery endpoint's own real, live ordering is the
        # deterministic selection (Module 6D Section 23), not a
        # separate sort this adapter imposes.
        seen: set[int] = set()
        ordered: list[int] = []
        for cik in ciks:
            if cik not in seen:
                seen.add(cik)
                ordered.append(cik)
        return ordered[:limit]

    def _fetch_company(self, cik: int, headers: dict[str, str]) -> CollectedItem:
        url = _SUBMISSIONS_URL.format(cik=cik)
        try:
            response = httpx.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise RetryableCollectorError(f"Timed out fetching {url}: {exc}") from exc
        except httpx.ConnectError as exc:
            raise RetryableCollectorError(f"Could not connect fetching {url}: {exc}") from exc
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise RetryableCollectorError(f"Network error fetching {url}: {exc}") from exc

        self._raise_for_status(response, f"SEC EDGAR submissions ({cik})")

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NonRetryableCollectorError(
                f"Malformed (non-JSON) response from {url}: {exc}"
            ) from exc

        return self._to_collected_item(body)

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code in (401, 403):
            raise NonRetryableCollectorError(
                f"{context}: authentication/identification failed (HTTP {response.status_code}) — "
                "check the configured user_agent. Retrying will not help."
            )
        if response.status_code == 404:
            raise NonRetryableCollectorError(f"{context}: not found (HTTP 404).")
        if response.status_code == 429:
            raise RetryableCollectorError(f"{context}: rate limit hit (HTTP 429).")
        if response.status_code >= 500:
            raise RetryableCollectorError(f"{context}: server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            raise NonRetryableCollectorError(f"{context}: unexpected HTTP {response.status_code}.")

    def _to_collected_item(self, body: dict[str, Any]) -> CollectedItem:
        cik_raw = body.get("cik")
        cik = str(cik_raw).zfill(10) if cik_raw is not None else None

        business_address = (body.get("addresses") or {}).get("business") or {}

        raw_content: dict[str, Any] = {
            "cik": cik,
            "name": _get(body.get("name")),
            "entity_type": _get(body.get("entityType")),
            "sic": _get(body.get("sic")),
            "sic_description": _get(body.get("sicDescription")),
            "ein": _get(body.get("ein")),
            "category": _get(body.get("category")),
            "fiscal_year_end": _get(body.get("fiscalYearEnd")),
            "state_of_incorporation": _get(body.get("stateOfIncorporation")),
            "tickers": _get(body.get("tickers")),
            "exchanges": _get(body.get("exchanges")),
            "phone": _get(body.get("phone")),
            "website": _get(body.get("website")),
            "business_address_street1": _get(business_address.get("street1")),
            "business_address_city": _get(business_address.get("city")),
            "business_address_state": _get(business_address.get("stateOrCountry")),
            "business_address_zip": _get(business_address.get("zipCode")),
            "former_names": _get(
                [fn.get("name") for fn in (body.get("formerNames") or []) if fn.get("name")]
            ),
        }
        return CollectedItem(
            raw_content=raw_content,
            content_hash=_content_hash(raw_content),
            external_identifier=cik,
        )

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "U.S. Securities and Exchange Commission",
            "dataset": "EDGAR company submissions",
            "license_reference": "U.S. government work — public domain",
            "population_note": (
                "Public/securities-issuing companies only — not a universal U.S. "
                "company registry (see docs/product/phase-6c-...-architecture.md Section 10)."
            ),
        }


__all__ = ["SECEdgarAdapter"]
