"""
Datatype/unit/enum validation — dispatches entirely on the target
ProductSpecification's own `datatype`, and runs strictly BEFORE any
ProductAttributeEvidence row is even considered by
app.services.spec_extraction_service. This is a deliberate, separate
layer, not folded into product_attribute_evidence_service: that
service's job is to persist an already-well-formed claim and run
conflict detection, not to re-derive parsing rules, and none of this
validation logic existed anywhere in the codebase before this
milestone (app.services.product_service's own attribute-setting path
only checks that a specification belongs to the product's category —
it never checks a value against datatype/enum_options).

A candidate that fails here never becomes a database row of any
status — not EXTRACTED, not REJECTED.
`app.models.provenance_record.ProvenanceStatus.REJECTED` is reserved,
everywhere else in this codebase
(product_attribute_evidence_service.reject_product_attribute_evidence),
for a status a human reviewer reaches on evidence that was already
looked at. A candidate that never became a well-formed claim was never
looked at by anyone — reusing REJECTED for it would let an admin
mistake "the parser gave up" for "a reviewer disagreed."
"""

from dataclasses import dataclass

from app.extraction import patterns, unit_conversion
from app.models.product_specification import ProductSpecification, SpecificationDataType

KNOWN_UNITS = unit_conversion.KNOWN_UNITS

# ProductAttribute.value is String(500) — a candidate that would
# silently truncate on eventual apply is rejected here instead, where
# the reason is still visible to a reviewer.
_MAX_TEXT_LENGTH = 500


@dataclass(frozen=True)
class ParsedReading:
    """One successfully validated reading of one specification, not yet
    reconciled against any other occurrence of the same specification
    in the same document — see spec_extraction_service for that step."""

    observed_value: str
    observed_unit: str | None
    normalized_value: str | None
    normalized_unit: str | None
    unit_resolved: bool


@dataclass(frozen=True)
class ValidationFailure:
    reason: str


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _with_unit(text: str, unit: str | None) -> str:
    """`value_observed` must faithfully represent what the source said
    — including its unit, never just the bare number — so a reviewer
    never has to cross-reference extraction_context.occurrences to see
    what was actually printed."""
    return f"{text} {unit}" if unit else text


def _numeric_reading(
    specification: ProductSpecification, number_text: str, unit: str | None
) -> ParsedReading | ValidationFailure:
    resolution = unit_conversion.resolve_unit(unit, specification.unit)
    if resolution.reject_reason is not None:
        return ValidationFailure(resolution.reject_reason)
    normalized_value: str | None = None
    normalized_unit: str | None = None
    if resolution.unit_resolved:
        normalized_unit = specification.unit
        if resolution.convert is not None:
            normalized_value = _format_number(resolution.convert(float(number_text)))
        else:
            normalized_value = _format_number(float(number_text))
    return ParsedReading(
        observed_value=_with_unit(number_text, unit),
        observed_unit=unit,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        unit_resolved=resolution.unit_resolved,
    )


def _range_reading(
    specification: ProductSpecification, low: str, high: str, unit: str | None
) -> ParsedReading | ValidationFailure:
    if float(low) > float(high):
        return ValidationFailure("range_min_exceeds_max")
    resolution = unit_conversion.resolve_unit(unit, specification.unit)
    if resolution.reject_reason is not None:
        return ValidationFailure(resolution.reject_reason)
    observed_value = _with_unit(f"{low} to {high}", unit)
    normalized_value: str | None = None
    normalized_unit: str | None = None
    if resolution.unit_resolved:
        normalized_unit = specification.unit
        if resolution.convert is not None:
            normalized_value = (
                f"{_format_number(resolution.convert(float(low)))} to "
                f"{_format_number(resolution.convert(float(high)))}"
            )
        else:
            normalized_value = f"{_format_number(float(low))} to {_format_number(float(high))}"
    return ParsedReading(
        observed_value=observed_value,
        observed_unit=unit,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        unit_resolved=resolution.unit_resolved,
    )


def _enum_reading(
    specification: ProductSpecification, value_text: str
) -> ParsedReading | ValidationFailure:
    options = specification.enum_options or []
    normalized_value = value_text.strip()
    normalized_lookup = {opt.strip().lower(): opt for opt in options}
    match = normalized_lookup.get(normalized_value.lower())
    if match is None:
        return ValidationFailure("enum_value_not_allowed")
    return ParsedReading(
        observed_value=match,
        observed_unit=None,
        normalized_value=None,
        normalized_unit=None,
        unit_resolved=True,
    )


def _text_reading(value_text: str) -> ParsedReading | ValidationFailure:
    trimmed = value_text.strip()
    if not trimmed:
        return ValidationFailure("empty_value")
    if len(trimmed) > _MAX_TEXT_LENGTH:
        return ValidationFailure("value_too_long")
    return ParsedReading(
        observed_value=trimmed,
        observed_unit=None,
        normalized_value=None,
        normalized_unit=None,
        unit_resolved=True,
    )


def validate_reading(
    specification: ProductSpecification, value_text: str
) -> ParsedReading | ValidationFailure:
    """
    Parses and validates `value_text` (the text found after a matched
    label) against `specification`'s own datatype/unit/enum_options.
    Every branch either returns a fully-formed ParsedReading or a
    ValidationFailure naming exactly why — nothing in between, nothing
    silently coerced.
    """
    datatype = specification.datatype

    if datatype == SpecificationDataType.NUMBER:
        numeric = patterns.parse_numeric_with_unit(value_text, KNOWN_UNITS)
        if numeric is None:
            if patterns.parse_range(value_text, KNOWN_UNITS) is not None:
                return ValidationFailure("range_not_allowed_for_number")
            return ValidationFailure("malformed_number")
        number_text, unit = numeric
        return _numeric_reading(specification, number_text, unit)

    if datatype == SpecificationDataType.RANGE:
        range_match = patterns.parse_range(value_text, KNOWN_UNITS)
        if range_match is None:
            if patterns.parse_numeric_with_unit(value_text, KNOWN_UNITS) is not None:
                return ValidationFailure("scalar_not_allowed_for_range")
            return ValidationFailure("malformed_range")
        low, high, unit = range_match
        return _range_reading(specification, low, high, unit)

    if datatype == SpecificationDataType.ENUM:
        return _enum_reading(specification, value_text)

    if datatype == SpecificationDataType.TEXT:
        return _text_reading(value_text)

    # BOOLEAN and any future datatype: no deterministic parsing rule is
    # defined for it in this milestone (see the design review's
    # explicit scope) — fails closed rather than guessing.
    return ValidationFailure("unsupported_datatype")


__all__ = ["ParsedReading", "ValidationFailure", "validate_reading"]
