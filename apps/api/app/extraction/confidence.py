"""
Four fixed confidence tiers — a lookup table over observable, already-
recorded flags, not a computed score. Nothing here is a statistical or
machine-learning estimate; every tier is fully reconstructable from
the same `match_type`/`match_style`/`unit_resolved`/`ambiguous` values
that also get written into ProductAttributeEvidence.extraction_context
(see app.services.spec_extraction_service), so a human reviewer can
always see exactly why a given tier was assigned.
"""

TIER_EXACT_NAME = 0.90
TIER_ALIAS = 0.70
TIER_WEAK = 0.45
TIER_AMBIGUOUS = 0.20


def compute_confidence(
    *, match_type: str, match_style: str, unit_resolved: bool, ambiguous: bool
) -> float:
    """
    match_type    "name"  -> the document used the specification's own
                              configured name, verbatim (after
                              normalization).
                  "alias" -> the document used a configured synonym —
                              one small extra inferential step behind a
                              verbatim name match, since an alias is a
                              human judgment call about equivalence
                              made at configuration time.
    match_style   "colon" -> a clean "Label: Value" line (strong).
                  "gap"   -> a weaker whitespace-run heuristic, used
                              only when no colon was present.
    unit_resolved  the observed unit matched the specification's unit
                   exactly, or was safely converted to it
                   (app.extraction.unit_conversion.resolve_unit).
    ambiguous      two or more valid occurrences of this specification
                   in the same document disagreed — always forces the
                   lowest tier, regardless of every other signal.
    """
    if ambiguous:
        return TIER_AMBIGUOUS
    if match_style != "colon" or not unit_resolved:
        return TIER_WEAK
    if match_type == "name":
        return TIER_EXACT_NAME
    return TIER_ALIAS


__all__ = [
    "TIER_ALIAS",
    "TIER_AMBIGUOUS",
    "TIER_EXACT_NAME",
    "TIER_WEAK",
    "compute_confidence",
]
