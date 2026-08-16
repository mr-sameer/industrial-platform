"""
Verification scoring configuration — Module 3B. This is the ONE place
scoring weights/thresholds live. Per the module brief ("never hardcode
scores, use configuration"), nothing in
app.services.verification_score_service contains a bare number — every
weight and threshold is read from here, so tuning the rules is a
one-file change, not a hunt through service logic.

Design: a fixed, ordered list of requirement "checks", each contributing
a weight toward the overall percentage, grouped by which
VerificationLevel they gate. This is a Python-level config today (see
docs/adr/0029's consequences for why: no product requirement yet to make
this admin-editable at runtime) — moving it to a database table or
feature-flag service later doesn't change VerificationScoreService's
logic, only where `VERIFICATION_REQUIREMENTS` is loaded from.
"""

from dataclasses import dataclass
from enum import StrEnum


class VerificationLevel(StrEnum):
    """Ordered — index in this enum IS the rank, used for comparisons."""

    UNVERIFIED = "unverified"
    EMAIL_VERIFIED = "email_verified"
    BUSINESS_VERIFIED = "business_verified"
    FACTORY_VERIFIED = "factory_verified"
    PREMIUM_VERIFIED = "premium_verified"


LEVEL_ORDER: list[VerificationLevel] = [
    VerificationLevel.UNVERIFIED,
    VerificationLevel.EMAIL_VERIFIED,
    VerificationLevel.BUSINESS_VERIFIED,
    VerificationLevel.FACTORY_VERIFIED,
    VerificationLevel.PREMIUM_VERIFIED,
]

# The percentage threshold at which a company reaches each level. A
# company's level is the highest level whose threshold its computed
# percentage meets — see VerificationScoreService.calculate.
LEVEL_THRESHOLDS: dict[VerificationLevel, int] = {
    VerificationLevel.UNVERIFIED: 0,
    VerificationLevel.EMAIL_VERIFIED: 20,
    VerificationLevel.BUSINESS_VERIFIED: 45,
    VerificationLevel.FACTORY_VERIFIED: 70,
    VerificationLevel.PREMIUM_VERIFIED: 90,
}


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    weight: int  # contribution toward the 0-100 percentage
    level: VerificationLevel  # which level this requirement is "for", shown in missing-requirements output


# Weights sum to 100. Grouped by level for readability; the sum, not the
# grouping, drives the percentage — see docs/architecture/company-verification-data-model.md
# for the full rationale of each requirement's presence/weight.
VERIFICATION_REQUIREMENTS: list[Requirement] = [
    # Email Verified (20 pts total)
    Requirement(
        "owner_email_verified",
        "Account owner's email is verified",
        20,
        VerificationLevel.EMAIL_VERIFIED,
    ),
    # Business Verified (25 pts total, on top of the above)
    Requirement(
        "legal_entity_type_set",
        "Legal entity type provided",
        6,
        VerificationLevel.BUSINESS_VERIFIED,
    ),
    Requirement(
        "government_id_set",
        "At least one government ID provided (GSTIN, PAN, or CIN)",
        7,
        VerificationLevel.BUSINESS_VERIFIED,
    ),
    Requirement(
        "business_registration_date_set",
        "Business registration date provided",
        4,
        VerificationLevel.BUSINESS_VERIFIED,
    ),
    Requirement(
        "business_registration_document_uploaded",
        "Business registration document uploaded",
        8,
        VerificationLevel.BUSINESS_VERIFIED,
    ),
    # Factory Verified (25 pts total, on top of the above)
    Requirement(
        "business_type_set",
        "Manufacturing/trading status specified",
        5,
        VerificationLevel.FACTORY_VERIFIED,
    ),
    Requirement(
        "factory_license_document_uploaded",
        "Factory license document uploaded",
        12,
        VerificationLevel.FACTORY_VERIFIED,
    ),
    Requirement(
        "manufacturing_categories_set",
        "Manufacturing categories specified",
        8,
        VerificationLevel.FACTORY_VERIFIED,
    ),
    # Premium Verified (30 pts total, on top of the above)
    Requirement("logo_uploaded", "Company logo uploaded", 5, VerificationLevel.PREMIUM_VERIFIED),
    Requirement(
        "cover_image_uploaded", "Cover image uploaded", 4, VerificationLevel.PREMIUM_VERIFIED
    ),
    Requirement(
        "descriptions_complete",
        "Short description, mission, and vision all provided",
        6,
        VerificationLevel.PREMIUM_VERIFIED,
    ),
    Requirement(
        "social_link_added", "At least one social link added", 4, VerificationLevel.PREMIUM_VERIFIED
    ),
    Requirement(
        "quality_certificate_uploaded",
        "A quality certificate uploaded (ISO, CE, or BIS)",
        8,
        VerificationLevel.PREMIUM_VERIFIED,
    ),
    Requirement(
        "export_categories_set",
        "Export capability and categories specified",
        3,
        VerificationLevel.PREMIUM_VERIFIED,
    ),
]

assert (
    sum(r.weight for r in VERIFICATION_REQUIREMENTS) == 100
), "VERIFICATION_REQUIREMENTS weights must sum to 100 — see this module's docstring"
