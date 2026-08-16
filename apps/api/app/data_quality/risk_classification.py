"""
Field risk classification — Module 5E, Section 11/12. A small, static,
documented mapping — deliberately not a database table, matching this
phase's own "only add schema where genuinely necessary" instruction:
the set of field names in play today is small and known (Module 5C's
real field mapping), and a Python mapping is easier to review and
change than a table would be for something this size. If the set of
fields grows large enough that this becomes unwieldy, promoting it to
configuration data (matching Phase 5's general "configuration, not
code" extensibility principle) is a natural, later step — not done
here because it isn't needed yet.

Company/Product fields (identified by ProvenanceRecord.field_name) are
classified independently of ProductSpecification's own risk_tier
column — the latter is category-author-controlled (Module 5E model
change), the former is this fixed, code-level mapping. Both answer the
same question ("how much verification effort does this field
deserve") for their respective entity types.
"""

from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Company fields — from the real field set Module 5C's adapter and
# Module 3B's own schema produce today. Anything not listed defaults
# to MEDIUM (see classify_company_field) — a deliberately cautious
# default: an unclassified field is treated as "worth a normal amount
# of care," never silently treated as low-stakes.
_COMPANY_FIELD_RISK: dict[str, RiskLevel] = {
    # Legal identity — getting these wrong is confusing, not dangerous.
    "name": RiskLevel.LOW,
    "company_name": RiskLevel.LOW,
    "legal_name": RiskLevel.LOW,
    "industry": RiskLevel.LOW,
    "principal_business_activity": RiskLevel.LOW,
    "registered_office_address": RiskLevel.LOW,
    "registered_state": RiskLevel.LOW,
    "city": RiskLevel.LOW,
    "state": RiskLevel.LOW,
    "country": RiskLevel.LOW,
    "sub_category": RiskLevel.LOW,
    "registrar_of_companies": RiskLevel.LOW,
    "date_of_registration": RiskLevel.LOW,
    "company_class": RiskLevel.LOW,
    "company_category": RiskLevel.LOW,
    # Medium — capability/website claims are meaningfully misleading
    # if wrong, but carry no physical-world consequence.
    "website": RiskLevel.MEDIUM,
    "company_status": RiskLevel.MEDIUM,
    "authorized_capital": RiskLevel.MEDIUM,
    "paid_up_capital": RiskLevel.MEDIUM,
    # High — compliance-adjacent identifiers and any certification
    # claim carry real legal/reputational consequence if false.
    "cin": RiskLevel.HIGH,
    "gst_number": RiskLevel.HIGH,
    "pan": RiskLevel.HIGH,
    "msme_number": RiskLevel.HIGH,
    "iec_number": RiskLevel.HIGH,
    "export_capable": RiskLevel.HIGH,
}


def classify_company_field(field_name: str) -> RiskLevel:
    return _COMPANY_FIELD_RISK.get(field_name, RiskLevel.MEDIUM)


def classify_field(entity_type: str, field_name: str) -> RiskLevel:
    """
    The one entry point this module exposes. `entity_type` matches
    app.models.provenance_record.EntityType's own values ("company" /
    "product") — for "product," risk lives on ProductSpecification.risk_tier
    (a real, per-specification column, Module 5E's model change) rather
    than this static mapping, so this function defers to that instead
    of duplicating a second classification for Product fields.
    """
    if entity_type == "company":
        return classify_company_field(field_name)
    # Product fields: risk is determined by the specific
    # ProductSpecification's own risk_tier, not by field_name alone —
    # callers with product context should read that column directly
    # (see app.services.data_quality_service). Field-name-only
    # classification for a product falls back to MEDIUM, the same
    # cautious default as an unclassified company field.
    return RiskLevel.MEDIUM
