"""
Deterministic label -> ProductSpecification resolution. Exact,
normalized set-membership only — no fuzzy matching, no Levenshtein
distance, no substring matching, no embeddings, no semantic
similarity, no LLM. A label either matches exactly one specification's
name or one of its SpecificationAlias rows, after identical
normalization on both sides, or it doesn't match at all.

Scoped by construction to whatever list of ProductSpecification rows
the caller passes in — app.services.spec_extraction_service always
passes only the target Product's own category's specifications, so a
label never matches across categories.
"""

import re
import uuid
from dataclasses import dataclass

from app.models.product_specification import ProductSpecification
from app.models.specification_alias import SpecificationAlias

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_label(text: str) -> str:
    """lowercase, trim, collapse internal whitespace, strip a trailing colon."""
    stripped = text.strip()
    if stripped.endswith(":"):
        stripped = stripped[:-1].strip()
    return _WHITESPACE_RUN.sub(" ", stripped).lower()


@dataclass(frozen=True)
class LabelIndex:
    # normalized label -> every (specification, match_type) that claims it.
    # More than one entry for a label is a configuration conflict, not
    # an extraction ambiguity — see resolve_label.
    by_label: dict[str, list[tuple[ProductSpecification, str]]]


def build_label_index(
    specifications: list[ProductSpecification],
    aliases_by_specification: dict[uuid.UUID, list[SpecificationAlias]],
) -> LabelIndex:
    by_label: dict[str, list[tuple[ProductSpecification, str]]] = {}
    for spec in specifications:
        by_label.setdefault(normalize_label(spec.name), []).append((spec, "name"))
        for alias_row in aliases_by_specification.get(spec.id, []):
            by_label.setdefault(normalize_label(alias_row.alias), []).append((spec, "alias"))
    return LabelIndex(by_label=by_label)


@dataclass(frozen=True)
class MatchResult:
    specification: ProductSpecification
    match_type: str  # "name" | "alias"


def resolve_label(
    index: LabelIndex, label_text: str
) -> MatchResult | list[ProductSpecification] | None:
    """
    Returns:
      - MatchResult for exactly one matching specification (the normal case)
      - None when nothing in this category claims the label
      - a list of >=2 specifications when more than one specification's
        name/alias set claims the same normalized label — a category
        authoring conflict the extractor must surface, never resolve by
        guessing which one was meant.
    """
    candidates = index.by_label.get(normalize_label(label_text))
    if not candidates:
        return None
    unique_specs = {spec.id: spec for spec, _match_type in candidates}
    if len(unique_specs) > 1:
        return list(unique_specs.values())
    specification, match_type = candidates[0]
    return MatchResult(specification=specification, match_type=match_type)


__all__ = ["LabelIndex", "MatchResult", "build_label_index", "normalize_label", "resolve_label"]
