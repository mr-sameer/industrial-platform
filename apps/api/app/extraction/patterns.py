"""
Deterministic line-shape and numeric/range token parsing — pure string
functions only, no database, no I/O. See app.extraction.validation for
how these combine with a target ProductSpecification's own datatype
and unit to become a validated reading or a documented rejection.

Every function here operates on one line of already-extracted page
text (app.collectors.pdf_text_extraction, unchanged) and is regex-only:
no fuzzy matching, no scoring, nothing probabilistic.
"""

import re
from dataclasses import dataclass

_NUMBER = r"-?\d+(?:\.\d+)?"
_NUMBER_RE = re.compile(rf"^({_NUMBER})$")
_NONNEG_NUMBER = r"\d+(?:\.\d+)?"

# "Label: Value" (or "Label : Value") — the strong, unambiguous shape.
# The label group excludes colons so a value containing further colons
# (e.g. "Standard: IS 9079: Rev 2") still splits on the first one only.
_COLON_SPLIT = re.compile(r"^\s*([^:\n]+?)\s*:\s*(\S.*?)\s*$")

# "Label<2+ spaces or a tab>Value" — a weaker, single-column-table
# heuristic used only when no colon is present. Deliberately requires a
# wide gap (never a single space) so ordinary prose is not misread as
# a label/value pair.
_GAP_SPLIT = re.compile(r"^\s*(\S(?:.*\S)?)(?:[ \t]{2,}|\t)(\S.*?)\s*$")

# Range separators. The dash form deliberately requires non-negative
# endpoints — a range with a negative endpoint (e.g. "-10 to 120 °C")
# must use the word form instead; a bare leading "-" before two dash-
# joined numbers is genuinely ambiguous between "a negative range
# start" and "a range separator", and this module never guesses which.
_RANGE_TO = re.compile(rf"^({_NUMBER})\s+to\s+({_NUMBER})\s*(\S.*)?$", re.IGNORECASE)
_RANGE_DASH = re.compile(rf"^({_NONNEG_NUMBER})\s*[-–]\s*({_NONNEG_NUMBER})\s*(\S.*)?$")


@dataclass(frozen=True)
class LineMatch:
    label_text: str
    value_text: str
    style: str  # "colon" | "gap"


def split_label_value(line: str) -> LineMatch | None:
    """
    Splits one line into a candidate (label, value) pair, or returns
    None if the line has neither shape. Colon is tried first and is the
    strong signal (see app.extraction.confidence); the whitespace-gap
    fallback is weaker and caps confidence accordingly.
    """
    if not line.strip():
        return None
    match = _COLON_SPLIT.match(line)
    if match:
        return LineMatch(label_text=match.group(1), value_text=match.group(2), style="colon")
    match = _GAP_SPLIT.match(line)
    if match:
        return LineMatch(label_text=match.group(1), value_text=match.group(2), style="gap")
    return None


def parse_numeric_with_unit(
    value_text: str, known_units: frozenset[str]
) -> tuple[str, str | None] | None:
    """
    Returns (numeric_string, unit_or_None) for a clean "<number>" or
    "<number><known unit>" shape with nothing left over, or None if the
    text isn't that shape at all (leftover characters, not a number,
    etc.) — never partially parsed, never guessed.
    """
    text = value_text.strip()
    for unit in sorted(known_units, key=len, reverse=True):
        if text.endswith(unit):
            number_part = text[: -len(unit)].strip()
            if _NUMBER_RE.match(number_part):
                return number_part, unit
    if _NUMBER_RE.match(text):
        return text, None
    return None


def parse_range(value_text: str, known_units: frozenset[str]) -> tuple[str, str, str | None] | None:
    """
    Returns (low, high, unit_or_None) for a recognized range shape
    ("10-50 m³/h", "20-80 m", "-10 to 120 °C"), or None if the text
    isn't a range at all. A trailing token that isn't a known unit is
    treated as malformed (returns None) rather than silently dropped.
    """
    text = value_text.strip()
    match = _RANGE_TO.match(text) or _RANGE_DASH.match(text)
    if not match:
        return None
    low, high, rest = match.group(1), match.group(2), (match.group(3) or "").strip()
    if not rest:
        return low, high, None
    for unit in sorted(known_units, key=len, reverse=True):
        if rest == unit:
            return low, high, unit
    return None


__all__ = ["LineMatch", "parse_numeric_with_unit", "parse_range", "split_label_value"]
