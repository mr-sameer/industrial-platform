"""
Normalization — Module 5C. Applied only at the point a reviewed raw
observation is being mapped toward candidate Company fields (see
app.services.company_promotion_service) — never at raw collection time
(app.collectors.mca_data_gov_in_adapter never calls this module,
deliberately: "preserve the original source value, never destroy the
original observation," per this module's own instruction).

Deliberately minimal — normalizes only what's justified per the
approved architecture (Section 7 of the Module 5C ticket): company
name whitespace/casing, and address parsing where the source's own
structure makes it safely possible (MCA's "Registered State" field is
already a distinct, structured field — no parsing needed for state;
city extraction from the free-text "Registered Office Address" is
attempted conservatively and returns None rather than guessing wrong).
"""

import re
from datetime import date, datetime

# MCA Company Master Data (per this pilot's confirmed field mapping,
# docs/product/phase-5c-india-company-data-source-architecture.md
# Section 4) covers only Indian-registered companies — "India" is a
# safe, source-wide constant here, not a per-record guess.
SOURCE_COUNTRY = "India"

# A 6-digit Indian postal code, commonly the last token in a registered
# office address — used only as an anchor to conservatively locate a
# preceding city name; never used to invent a value when absent.
_PIN_CODE_PATTERN = re.compile(r"\b\d{6}\b")


def normalize_company_name(raw_name: str) -> str:
    """Whitespace/casing normalization only — never changes the
    company's actual registered name, only its formatting for
    consistent storage and future matching (Phase 5 architecture
    Section 8's medium-tier name-matching signal)."""
    return " ".join(raw_name.split()).strip()


def attempt_city_from_address(address: str | None, known_state: str | None = None) -> str | None:
    """
    A conservative, best-effort extraction — returns None rather than
    a low-confidence guess whenever the address doesn't match a
    recognizable shape. Looks for a comma-separated segment
    immediately before a 6-digit PIN code, which is a common (not
    universal) convention in Indian registered-address formatting.

    `known_state`, when provided (MCA's own "Registered State" field is
    already structured — Section 4 of the architecture doc — so this
    is normally available), is used to disambiguate: Indian addresses
    commonly end "...City, State PINCODE", meaning the segment
    immediately before the PIN code is frequently the *state*, not the
    city — found via direct testing against a real-shaped example
    address, not assumed. When the segment nearest the PIN code
    matches the known state (case-insensitively), the segment before
    *that* is used as the city candidate instead. Without a known
    state to disambiguate, this function is deliberately more
    conservative and returns None rather than risk the same
    state-mistaken-for-city error.

    This is explicitly NOT a general-purpose address parser — a
    genuinely bounded, honestly-limited heuristic, matching the
    architecture document's own caution (Section 4: "a real, bounded
    parsing task... not invented here").
    """
    if not address:
        return None
    match = _PIN_CODE_PATTERN.search(address)
    if not match:
        return None
    before_pin = address[: match.start()].rstrip(" ,-")
    segments = [seg.strip() for seg in before_pin.split(",") if seg.strip()]
    if not segments:
        return None

    last_segment = segments[-1]
    if known_state and last_segment.lower() == known_state.strip().lower():
        # The segment nearest the PIN code is the (already-known)
        # state, not a new city finding — the real city candidate, if
        # any, is the segment before it.
        return segments[-2] if len(segments) >= 2 else None

    if known_state is None:
        # No independent state to disambiguate against — too likely to
        # silently return a state name mislabeled as a city (the exact
        # failure mode found via direct testing). Honest None beats a
        # confident-looking wrong answer.
        return None

    return last_segment


# Format not independently confirmed via a live API response (see
# app.collectors.mca_data_gov_in_adapter's module docstring for why) —
# DD/MM/YYYY is the conventional Indian date format and the most
# likely candidate, tried first; ISO 8601 as a fallback. Returns None
# rather than guessing at an ambiguous or unparseable value — a
# registration date this function can't confidently parse is left
# unmapped (Company.business_registration_date stays unset for that
# record) rather than risking a silently wrong day/month swap.
_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")


def parse_registration_date(raw_value: str | None) -> date | None:
    if not raw_value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw_value.strip(), fmt).date()
        except ValueError:
            continue
    return None
