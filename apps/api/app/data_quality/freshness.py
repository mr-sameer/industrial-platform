"""
Freshness policy — Module 5E, Section 5. Category-based thresholds, no
single universal period, per the approved architecture's explicit
instruction. A static, documented configuration (not a database
table) — matching the same "small, known set, easier to review as
code" reasoning as app.data_quality.risk_classification.
"""

from datetime import UTC, datetime, timedelta
from enum import Enum


class FreshnessState(str, Enum):
    FRESH = "fresh"
    APPROACHING_STALE = "approaching_stale"
    STALE = "stale"


# Field-category cadences from the architecture doc's Section 5 table,
# expressed as real durations. "Approaching stale" begins at 80% of
# the threshold, per that section's own proposed rule.
_LEGAL_IDENTITY_FIELDS = frozenset(
    {
        "name",
        "company_name",
        "legal_name",
        "cin",
        "business_registration_date",
        "date_of_registration",
        "registrar_of_companies",
        "company_class",
        "company_category",
    }
)
_ADDRESS_FIELDS = frozenset(
    {"country", "state", "city", "registered_state", "registered_office_address"}
)
_CAPABILITY_FIELDS = frozenset({"industry", "principal_business_activity", "company_status"})

_CATEGORY_THRESHOLDS: dict[str, timedelta] = {
    "legal_identity": timedelta(days=180),
    "address": timedelta(days=90),
    "capability": timedelta(days=30),
    "default": timedelta(days=30),
}


def _category_for_field(field_name: str) -> str:
    if field_name in _LEGAL_IDENTITY_FIELDS:
        return "legal_identity"
    if field_name in _ADDRESS_FIELDS:
        return "address"
    if field_name in _CAPABILITY_FIELDS:
        return "capability"
    return "default"


def stale_threshold_for_field(field_name: str) -> timedelta:
    return _CATEGORY_THRESHOLDS[_category_for_field(field_name)]


def classify_freshness(
    field_name: str, last_observed_at: datetime, *, now: datetime | None = None
) -> FreshnessState:
    """
    Certifications are deliberately NOT handled by this generic,
    calendar-based function — per the architecture doc's Section 5,
    certification freshness is expiration-sensitive
    (VerificationDocument.expiry_date / ProvenanceRecord.expires_at),
    not calendar-sensitive, and belongs to a distinct check
    (see app.services.data_quality_service's expiry handling) rather
    than being forced through this threshold-based model.
    """
    current = now or datetime.now(UTC)
    threshold = stale_threshold_for_field(field_name)
    age = current - last_observed_at
    if age >= threshold:
        return FreshnessState.STALE
    if age >= threshold * 0.8:
        return FreshnessState.APPROACHING_STALE
    return FreshnessState.FRESH
