"""
Spec extraction service — orchestrates the approved deterministic
specification-extraction milestone. Reads an already-existing
RawObservation's page text (produced earlier, unchanged, by
app.collectors.document_extraction_adapter) against an already-existing
Product's already-existing ProductSpecifications, and creates
ProductAttributeEvidence rows through the existing, unmodified
app.services.product_attribute_evidence_service.create_attribute_evidence
— never a parallel persistence path, never a shortcut around it.

This module owns exactly one thing product_attribute_evidence_service
does not: turning raw page text into validated
(specification_id, value_observed, confidence, extraction_context)
candidates. It does not duplicate that service's own logic (creation,
idempotency, conflict detection) — see `run_extraction`'s use of
`create_attribute_evidence` below, called unchanged, once per
specification with at least one valid reading.

Every row this module creates uses extraction_method=RULE_BASED and
status=EXTRACTED. Nothing here ever calls verify/reject/apply, and
nothing here ever touches ProductAttribute directly — the existing
human-review lifecycle is entirely untouched.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction import label_matching, patterns, validation
from app.extraction.candidates import (
    AmbiguousConfigurationEntry,
    ExtractionRunResult,
    RejectedCandidate,
)
from app.extraction.confidence import compute_confidence
from app.models.product_attribute_evidence import ProductAttributeEvidence
from app.models.product_specification import ProductSpecification, SpecificationDataType
from app.models.provenance_record import ExtractionMethod, ProvenanceStatus
from app.models.specification_alias import SpecificationAlias
from app.schemas.product_attribute_evidence import ProductAttributeEvidenceCreate
from app.services import product_attribute_evidence_service, product_service, provenance_service

__all__ = [
    "InvalidDocumentStructureError",
    "ProductNotFoundForExtractionError",
    "RawObservationNotFoundForExtractionError",
    "run_extraction",
]

_RELATIVE_TOLERANCE = 0.005

_EXTRACTION_RULE_BY_DATATYPE: dict[SpecificationDataType, str] = {
    SpecificationDataType.NUMBER: "numeric_with_unit",
    SpecificationDataType.RANGE: "range",
    SpecificationDataType.ENUM: "enum_exact",
    SpecificationDataType.TEXT: "text",
}


class ProductNotFoundForExtractionError(Exception):
    pass


class RawObservationNotFoundForExtractionError(Exception):
    pass


class InvalidDocumentStructureError(Exception):
    """Raised when raw_observation.raw_content isn't the page-numbered
    document-extraction shape this extractor requires — see
    app.collectors.document_extraction_adapter's own raw_content
    contract, which this check mirrors without importing that module
    (this milestone must not modify or couple to Checkpoint 1's code)."""


@dataclass(frozen=True)
class _PageText:
    number: int
    text: str


@dataclass(frozen=True)
class _RawReading:
    page: int
    line_index: int
    snippet: str
    style: str
    match_type: str
    matched_label: str
    extraction_rule: str
    parsed: validation.ParsedReading


def _extract_pages(raw_content: dict[str, object]) -> list[_PageText]:
    pages = raw_content.get("pages")
    if not isinstance(pages, list) or not pages:
        raise InvalidDocumentStructureError(
            "raw_observation.raw_content has no non-empty 'pages' list — "
            "this is not a document-extraction RawObservation."
        )
    result: list[_PageText] = []
    for entry in pages:
        if not isinstance(entry, dict):
            raise InvalidDocumentStructureError("raw_content.pages entries must be objects.")
        page_number = entry.get("page")
        text = entry.get("text")
        if not isinstance(page_number, int) or not isinstance(text, str):
            raise InvalidDocumentStructureError(
                "raw_content.pages entries must each have an integer 'page' and a string 'text'."
            )
        result.append(_PageText(number=page_number, text=text))
    return result


async def _load_aliases(
    db: AsyncSession, specification_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[SpecificationAlias]]:
    if not specification_ids:
        return {}
    result = await db.execute(
        select(SpecificationAlias).where(SpecificationAlias.specification_id.in_(specification_ids))
    )
    grouped: dict[uuid.UUID, list[SpecificationAlias]] = defaultdict(list)
    for alias_row in result.scalars().all():
        grouped[alias_row.specification_id].append(alias_row)
    return grouped


async def _find_existing_evidence(
    db: AsyncSession,
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    raw_observation_id: uuid.UUID,
) -> ProductAttributeEvidence | None:
    result = await db.execute(
        select(ProductAttributeEvidence).where(
            ProductAttributeEvidence.product_id == product_id,
            ProductAttributeEvidence.specification_id == specification_id,
            ProductAttributeEvidence.raw_observation_id == raw_observation_id,
        )
    )
    return result.scalar_one_or_none()


def _values_within_tolerance(a: float, b: float) -> bool:
    denominator = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denominator <= _RELATIVE_TOLERANCE


def _readings_agree(
    specification: ProductSpecification,
    a: validation.ParsedReading,
    b: validation.ParsedReading,
) -> bool:
    """
    Two valid readings of the same specification "agree" only when it
    can be *proven* — via an exact match or a safe, allow-listed unit
    conversion (app.extraction.unit_conversion). Never asserted from an
    unresolved/unsafe unit pairing (e.g. one reading in HP, one in kW):
    that case falls through to the raw exact-match check below, which
    fails, correctly forcing ambiguity rather than guessing agreement.
    """
    datatype = specification.datatype
    if datatype == SpecificationDataType.NUMBER:
        if a.normalized_value is not None and b.normalized_value is not None:
            return _values_within_tolerance(float(a.normalized_value), float(b.normalized_value))
        return a.observed_value == b.observed_value and a.observed_unit == b.observed_unit
    if datatype == SpecificationDataType.RANGE:
        if a.normalized_value is not None and b.normalized_value is not None:
            a_low, a_high = (float(x) for x in a.normalized_value.split(" to "))
            b_low, b_high = (float(x) for x in b.normalized_value.split(" to "))
            return _values_within_tolerance(a_low, b_low) and _values_within_tolerance(
                a_high, b_high
            )
        return a.observed_value == b.observed_value and a.observed_unit == b.observed_unit
    return a.observed_value.strip().lower() == b.observed_value.strip().lower()


def _reconcile(
    specification: ProductSpecification, readings: list[_RawReading]
) -> tuple[_RawReading, list[dict[str, object]], bool]:
    """
    Combines every valid occurrence of one specification found anywhere
    in the document into: a deterministic representative occurrence
    (the earliest in page/line order), the full occurrence list (never
    dropped, regardless of agreement), and whether they disagree.
    """
    ordered = sorted(readings, key=lambda r: (r.page, r.line_index))
    representative = ordered[0]
    ambiguous = any(
        not _readings_agree(specification, representative.parsed, other.parsed)
        for other in ordered[1:]
    )
    occurrences: list[dict[str, object]] = [
        {
            "page": r.page,
            "value": r.parsed.observed_value,
            "unit": r.parsed.observed_unit,
            "snippet": r.snippet,
        }
        for r in ordered
    ]
    return representative, occurrences, ambiguous


async def run_extraction(
    db: AsyncSession, *, product_id: uuid.UUID, raw_observation_id: uuid.UUID
) -> ExtractionRunResult:
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise ProductNotFoundForExtractionError(str(product_id))

    observation = await provenance_service.get_raw_observation(db, raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundForExtractionError(str(raw_observation_id))

    pages = _extract_pages(observation.raw_content)

    specifications = await product_service.list_specifications_for_category(db, product.category_id)
    spec_by_id = {spec.id: spec for spec in specifications}
    aliases_by_spec = await _load_aliases(db, list(spec_by_id))
    index = label_matching.build_label_index(specifications, aliases_by_spec)

    readings_by_spec: dict[uuid.UUID, list[_RawReading]] = defaultdict(list)
    rejected: list[RejectedCandidate] = []
    ambiguous_configs: dict[str, set[uuid.UUID]] = {}

    for page in pages:
        for line_index, line in enumerate(page.text.splitlines()):
            split = patterns.split_label_value(line)
            if split is None:
                continue
            match = label_matching.resolve_label(index, split.label_text)
            if match is None:
                continue
            if isinstance(match, list):
                label_key = split.label_text.strip()
                ambiguous_configs.setdefault(label_key, set()).update(spec.id for spec in match)
                continue

            specification = match.specification
            outcome = validation.validate_reading(specification, split.value_text)
            if isinstance(outcome, validation.ValidationFailure):
                rejected.append(
                    RejectedCandidate(
                        page=page.number,
                        label=split.label_text.strip(),
                        reason=outcome.reason,
                    )
                )
                continue

            readings_by_spec[specification.id].append(
                _RawReading(
                    page=page.number,
                    line_index=line_index,
                    snippet=line.strip()[:240],
                    style=split.style,
                    match_type=match.match_type,
                    matched_label=split.label_text.strip(),
                    extraction_rule=_EXTRACTION_RULE_BY_DATATYPE[specification.datatype],
                    parsed=outcome,
                )
            )

    created: list[uuid.UUID] = []
    existing: list[uuid.UUID] = []

    for specification_id, readings in readings_by_spec.items():
        specification = spec_by_id[specification_id]
        representative, occurrences, ambiguous = _reconcile(specification, readings)
        conf = compute_confidence(
            match_type=representative.match_type,
            match_style=representative.style,
            unit_resolved=representative.parsed.unit_resolved,
            ambiguous=ambiguous,
        )
        extraction_context: dict[str, object] = {
            "page": representative.page,
            "snippet": representative.snippet,
            "matched_label": representative.matched_label,
            "match_type": representative.match_type,
            "match_style": representative.style,
            "extraction_rule": representative.extraction_rule,
            "occurrences": occurrences,
            "ambiguous": ambiguous,
        }

        pre_existing = await _find_existing_evidence(
            db, product_id, specification_id, raw_observation_id
        )
        if pre_existing is not None:
            existing.append(pre_existing.id)
            continue

        payload = ProductAttributeEvidenceCreate(
            product_id=product_id,
            specification_id=specification_id,
            raw_observation_id=raw_observation_id,
            value_observed=representative.parsed.observed_value,
            extraction_method=ExtractionMethod.RULE_BASED,
            confidence=conf,
            status=ProvenanceStatus.EXTRACTED,
            extraction_context=extraction_context,
        )
        evidence, _conflict = await product_attribute_evidence_service.create_attribute_evidence(
            db, payload
        )
        created.append(evidence.id)

    return ExtractionRunResult(
        created=created,
        existing=existing,
        rejected=rejected,
        ambiguous_configuration=[
            AmbiguousConfigurationEntry(label=label, specification_ids=sorted(spec_ids, key=str))
            for label, spec_ids in ambiguous_configs.items()
        ],
    )
