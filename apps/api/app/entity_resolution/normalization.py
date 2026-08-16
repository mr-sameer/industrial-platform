"""
Normalization for identity matching — Module 5D. Distinct from
app.collectors.normalization (which parses MCA-specific raw fields
like addresses/dates for the Company field mapping, Module 5C) — this
module normalizes values purely for *comparison* purposes during
candidate generation (app.entity_resolution.matching). Nothing here is
ever written back to a Company row or a RawObservation — normalized
forms exist only transiently, for the duration of a matching
computation.

Preserve original values: this module NEVER mutates the raw
observation or the Company record it's comparing — every function
here is a pure str -> str transform with no side effects, called only
at comparison time.
"""

import difflib
import re
import unicodedata

# Common Indian and general legal-entity suffixes, ordered longest-first
# so a longer, more specific suffix strips before a shorter substring of
# it might. Deliberately a fixed, documented list — not a "smart" NLP
# suffix detector — matching the same "no giant taxonomy built
# prematurely" discipline established throughout this project (Phase 5
# architecture doc, Section 9).
_LEGAL_SUFFIXES = [
    "private limited",
    "pvt limited",
    "pvt ltd",
    "public limited",
    "limited liability partnership",
    "limited",
    "incorporated",
    "corporation",
    "company",
    "llp",
    "ltd",
    "inc",
    "corp",
    "co",
]


def normalize_company_name_for_matching(raw_name: str) -> str:
    """
    Unicode-normalizes, uppercases, strips punctuation, collapses
    whitespace, and strips a trailing legal-entity suffix if present —
    "ABC Engineering Pvt. Ltd." and "ABC Engineering Private Limited"
    both normalize to "ABC ENGINEERING", matching the exact example in
    this module's own ticket. The *raw* value is never touched by this
    function — it only ever returns a new string for comparison.
    """
    value = unicodedata.normalize("NFKC", raw_name)
    value = value.upper()
    value = re.sub(r"[^\w\s]", "", value, flags=re.UNICODE)
    value = " ".join(value.split())

    for suffix in _LEGAL_SUFFIXES:
        suffix_upper = suffix.upper()
        if value.endswith(" " + suffix_upper):
            value = value[: -(len(suffix_upper) + 1)].strip()
            break
        if value == suffix_upper:
            # A bare legal suffix with nothing else — stripping would
            # leave an empty string, which is never useful for
            # matching; leave it as-is rather than produce "".
            break

    return value


def normalize_domain(website: str | None) -> str | None:
    """Strips scheme and 'www.', lowercases, strips a trailing slash —
    "https://www.Example.com/" and "example.com" both normalize to
    "example.com". Returns None for an empty/missing input rather than
    an empty string, so callers can distinguish "no website" from "a
    website that normalized to nothing" (the latter shouldn't happen,
    but None is the more honest signal either way)."""
    if not website:
        return None
    value = website.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = value.rstrip("/")
    return value or None


def normalize_location_component(value: str | None) -> str | None:
    """Same uppercase/whitespace normalization as company names, but
    without legal-suffix stripping (irrelevant for a city/state name) —
    used to compare Company.city/Company.state against a candidate's
    corresponding values for the 'strong address match' signal."""
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).upper()
    normalized = re.sub(r"[^\w\s]", "", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    return normalized or None


def fuzzy_name_similarity(name_a: str, name_b: str) -> float:
    """
    A permissive, WEAK-tier-only signal (per this module's own
    identity-priority ordering — fuzzy similarity is explicitly the
    *last* resort, never sufficient alone for anything above
    REVIEW_REQUIRED). Uses Python's standard-library
    difflib.SequenceMatcher rather than a bundled fuzzy-matching
    dependency — simple, deterministic, and exactly proportionate to
    how much weight this signal is actually given in the rules
    (app.entity_resolution.matching): a coarse "roughly similar or
    not" check, not a precision string-distance algorithm.
    """
    return difflib.SequenceMatcher(None, name_a, name_b).ratio()
